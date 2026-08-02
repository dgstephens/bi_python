import os
import sys
from datetime import datetime
from typing import Optional, List

import readchar
import questionary
from InquirerPy import inquirer as _inquirer
from rich.console import Console
from rich.markup import escape
from rich.table import Table
from rich.panel import Panel
from rich import box

import config
import api as api_module
from api import APIError
from forms import run_bin_form, run_item_form
from images import render_image

console = Console()

STYLE = questionary.Style([
    ("qmark", "fg:#00d7ff bold"),
    ("question", "bold"),
    ("answer", "fg:#00d7ff bold"),
    ("pointer", "fg:#00d7ff bold"),
    ("highlighted", "fg:#00d7ff bold"),
    ("selected", "fg:#00d7ff"),
    ("separator", "fg:#555555"),
    ("instruction", "fg:#555555"),
])


# ── Helpers ───────────────────────────────────────────────────────────────────

def fmt_date(date_str: Optional[str]) -> str:
    if not date_str:
        return ""
    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d")
    except Exception:
        return date_str[:10] if len(date_str) >= 10 else date_str


def show_error(msg: str) -> None:
    console.print(Panel(f"[red]{msg}[/red]", title="[red]Error[/red]", border_style="red"))


def show_success(msg: str) -> None:
    console.print(Panel(f"[green]{msg}[/green]", title="[green]Success[/green]", border_style="green"))


def ask(prompt: str, default: str = "") -> str:
    result = questionary.text(prompt, default=default, style=STYLE).ask()
    return result if result is not None else default


def ask_password(prompt: str) -> str:
    result = questionary.password(prompt, style=STYLE).ask()
    return result or ""


def confirm(prompt: str, default: bool = False) -> bool:
    result = questionary.confirm(prompt, default=default, style=STYLE).ask()
    return result if result is not None else default


def sel(prompt: str, choices: list):
    """Wrapper around questionary.select that returns the choice value or None."""
    return questionary.select(prompt, choices=choices, style=STYLE).ask()


def _fuzzy_pick(prompt: str, choices: list):
    """Fuzzy finder: full list shown, type to filter, arrow keys to scroll.

    *choices* is a list of dicts with "name" (display) and "value" (returned).
    Returns the selected value, or None if cancelled (Ctrl+C / Escape).
    """
    try:
        return _inquirer.fuzzy(
            message=prompt,
            choices=choices,
            max_height="70%",
            border=True,
            match_exact=False,
            keybindings={"skip": [{"key": "escape"}]},
        ).execute()
    except KeyboardInterrupt:
        return None


def shortcut_menu(prompt: str, items: list):
    """Single-keypress shortcut menu.

    items: list of (label, shortcut_char, value) tuples, or None for a separator.
    Displays each item as:  [X]  Label
    Press the shortcut key to select immediately. Ctrl-C or Escape returns None.
    """
    key_map = {}

    console.print()
    if prompt:
        console.print(f"  [bold]{prompt}[/bold]")
        console.print()

    for item in items:
        if item is None:
            console.print("  [dim]──────────────────[/dim]")
            continue
        label, shortcut, value = item
        key_map[shortcut.lower()] = value
        console.print(f"  [bold cyan]{escape('[' + shortcut.upper() + ']')}[/bold cyan]  {label}")

    console.print()

    while True:
        key = readchar.readkey()
        if key in ('\x03', '\x1b'):   # Ctrl-C or Escape
            return None
        if key.lower() in key_map:
            return key_map[key.lower()]


def ask_file_paths(prompt: str = "Image file paths (comma-separated, or Enter to skip):") -> List[str]:
    raw = ask(prompt)
    if not raw:
        return []
    paths = [p.strip() for p in raw.split(",") if p.strip()]
    valid = []
    for p in paths:
        if os.path.exists(p):
            valid.append(p)
        else:
            console.print(f"  [yellow]File not found, skipping:[/yellow] {p}")
    return valid


def _bin_id_from_item(item: dict) -> str:
    bid = item.get("binId")
    if isinstance(bid, dict):
        return bid.get("id", "")
    return bid or ""


def _bin_name_from_item(item: dict) -> str:
    bid = item.get("binId")
    if isinstance(bid, dict):
        return bid.get("binName", "")
    return ""


def _prev_bin_id_from_item(item: dict) -> str:
    pb = item.get("prevBin")
    if isinstance(pb, dict):
        return pb.get("id", "")
    return pb or ""


def _prev_bin_name_from_item(item: dict) -> str:
    pb = item.get("prevBin")
    if isinstance(pb, dict):
        return pb.get("binName", "")
    return ""


def _item_images(item: dict) -> List[str]:
    imgs = item.get("images") or []
    if not imgs and item.get("image"):
        imgs = [item["image"]]
    return [u for u in imgs if u]


# ── Auth ──────────────────────────────────────────────────────────────────────

def login_view(cfg: dict, client: api_module.BinInventoryAPI) -> dict:
    console.print()
    console.print(Panel(
        "[bold cyan]BinInventory CLI[/bold cyan]\n"
        "[dim]Personal inventory management[/dim]",
        border_style="cyan",
        padding=(1, 4),
    ))

    while True:
        action = sel("", [
            questionary.Choice("Login", value="login"),
            questionary.Choice("Sign up", value="signup"),
            questionary.Separator(),
            questionary.Choice("Exit", value="exit"),
        ])

        if action is None or action == "exit":
            sys.exit(0)

        if action == "login":
            email = ask("Email:")
            if not email:
                continue
            password = ask_password("Password:")
            if not password:
                continue
            try:
                result = client.login(email, password)
                cfg.update({
                    "token": result["token"],
                    "userId": result["userId"],
                    "email": result["email"],
                })
                config.save(cfg)
                client.token = result["token"]
                show_success(f"Logged in as {email}")
                return cfg
            except APIError as e:
                show_error(str(e))

        elif action == "signup":
            name = ask("Name:")
            email = ask("Email:")
            password = ask_password("Password (min 8 chars):")
            show = confirm("Show profile on the users page?")
            image_paths = ask_file_paths("Profile image path (or Enter to skip):")
            try:
                result = client.signup(
                    name=name,
                    email=email,
                    password=password,
                    show_on_users_page=show,
                    image_path=image_paths[0] if image_paths else None,
                )
                cfg.update({
                    "token": result["token"],
                    "userId": result["userId"],
                    "email": result["email"],
                })
                config.save(cfg)
                client.token = result["token"]
                show_success(f"Account created! Logged in as {email}")
                return cfg
            except APIError as e:
                show_error(str(e))


# ── Main menu ─────────────────────────────────────────────────────────────────

def main_menu(cfg: dict, client: api_module.BinInventoryAPI) -> None:
    while True:
        try:
            count_data = client.get_item_count(cfg["userId"])
            item_count = count_data.get("number", "?")
        except APIError:
            item_count = "?"

        console.print()
        console.print(Panel(
            f"[bold cyan]BinInventory CLI[/bold cyan]\n"
            f"[dim]Logged in as:[/dim] [cyan]{cfg.get('email', '')}[/cyan]  "
            f"[dim]Total items:[/dim] [cyan]{item_count}[/cyan]",
            border_style="cyan",
            padding=(0, 2),
        ))

        mode = cfg.get("image_mode", "none")
        mode_label = {"none": "No images", "ansi": "ANSI color", "ascii": "ASCII art"}.get(mode, mode)
        action = shortcut_menu("Main menu:", [
            ("My Bins",                        'b', "bins"),
            ("My Items",                       'i', "items"),
            ("Search Items",                   's', "search"),
            ("Shared Bins",                    'h', "shared"),   # sHared
            ("My Profile",                     'p', "profile"),
            (f"Settings  (images: {mode_label})", 't', "settings"),  # seTtings
            None,
            ("Logout",                         'l', "logout"),
            ("Exit",                           'x', "exit"),
        ])

        if action is None or action == "exit":
            sys.exit(0)
        elif action == "logout":
            config.clear_auth(cfg)
            client.token = None
            console.print("[cyan]Logged out.[/cyan]")
            cfg = login_view(cfg, client)
        elif action == "bins":
            bins_menu(cfg, client)
        elif action == "items":
            all_items_menu(cfg, client)
        elif action == "search":
            search_menu(cfg, client)
        elif action == "shared":
            shared_bins_menu(cfg, client)
        elif action == "profile":
            profile_menu(cfg, client)
        elif action == "settings":
            settings_menu(cfg)


# ── Bins ──────────────────────────────────────────────────────────────────────

def _print_bins_table(bins: list) -> None:
    table = Table(box=box.ROUNDED, show_header=True, header_style="bold cyan", padding=(0, 1))
    table.add_column("#", style="dim", width=4)
    table.add_column("Name", min_width=22)
    table.add_column("Location", min_width=14)
    table.add_column("Type", min_width=12)
    table.add_column("Public", width=8)
    table.add_column("Items", justify="right", width=6)

    for i, b in enumerate(bins, 1):
        table.add_row(
            str(i),
            b.get("binName", ""),
            b.get("location", "") or "",
            b.get("type", "") or "",
            "[green]Yes[/green]" if b.get("public") else "No",
            str(len(b.get("items", []))),
        )
    console.print()
    console.print(table)


def bins_menu(cfg: dict, client: api_module.BinInventoryAPI) -> None:
    while True:
        try:
            data = client.get_bins_by_user(cfg["userId"])
            bins = data.get("bins", [])
        except APIError as e:
            show_error(str(e))
            return

        choices = [
            {
                "name": (
                    b["binName"]
                    + (f"  [{b['location']}]" if b.get("location") else "")
                    + (f"  • {b['type']}" if b.get("type") else "")
                    + f"  ({len(b.get('items', []))} items)"
                ),
                "value": ("open", b),
            }
            for b in bins
        ] + [
            {"name": "+ New Bin", "value": ("new", None)},
            {"name": "← Back",   "value": ("back", None)},
        ]

        result = _fuzzy_pick(f"My Bins ({len(bins)}):", choices)
        if result is None:
            return
        action, payload = result

        if action == "back":
            return
        elif action == "new":
            create_bin_view(cfg, client)
        elif action == "open":
            bin_detail_menu(cfg, client, payload)


def bin_detail_menu(cfg: dict, client: api_module.BinInventoryAPI, bin_data: dict) -> None:
    while True:
        b = bin_data
        shared = ", ".join(b.get("sharedWith", [])) or "—"
        details = (
            f"[bold]{b.get('binName', '')}[/bold]\n\n"
            f"  [dim]Description:[/dim] {b.get('description', '') or '—'}\n"
            f"  [dim]Location:[/dim]    {b.get('location', '') or '—'}\n"
            f"  [dim]Type:[/dim]        {b.get('type', '') or '—'}\n"
            f"  [dim]Public:[/dim]      {'[green]Yes[/green]' if b.get('public') else 'No'}\n"
            f"  [dim]Shared with:[/dim] {shared}\n"
            f"  [dim]Items:[/dim]       {len(b.get('items', []))}"
        )
        console.print()
        console.print(Panel(details, title="Bin Details", border_style="cyan", padding=(0, 1)))
        render_image(b.get("image", ""), cfg.get("image_mode", "none"))

        action = shortcut_menu("Bin actions:", [
            ("View Items in this Bin", 'v', "items"),
            ("Edit Bin",               'e', "edit"),
            ("Delete Bin",             'd', "delete"),
            None,
            ("Back",                   'b', "back"),
        ])

        if action is None or action == "back":
            return
        elif action == "items":
            items_in_bin_menu(cfg, client, b)
        elif action == "edit":
            updated = edit_bin_view(cfg, client, b)
            if updated:
                bin_data = updated
        elif action == "delete":
            if confirm(f"Delete '{b['binName']}'? Items will be moved to 'no bin'."):
                try:
                    client.delete_bin(b["id"])
                    show_success("Bin deleted.")
                    return
                except APIError as e:
                    show_error(str(e))


def create_bin_view(cfg: dict, client: api_module.BinInventoryAPI) -> None:
    result = run_bin_form()
    if result is None:
        return
    try:
        client.create_bin(
            bin_name=result["bin_name"],
            description=result["description"],
            location=result["location"],
            bin_type=result["bin_type"],
            public=result["public"],
            user_id=cfg["userId"],
            sw_emails=result["sw_emails"],
            image_path=result["image_path"],
        )
        show_success(f"Bin '{result['bin_name']}' created.")
    except APIError as e:
        show_error(str(e))


def edit_bin_view(cfg: dict, client: api_module.BinInventoryAPI, b: dict) -> Optional[dict]:
    result = run_bin_form(existing=b)
    if result is None:
        return None
    try:
        updated = client.update_bin(
            bin_id=b["id"],
            bin_name=result["bin_name"],
            description=result["description"],
            location=result["location"],
            bin_type=result["bin_type"],
            public=result["public"],
            user_id=cfg["userId"],
            sw_emails=result["sw_emails"],
            image_path=result["image_path"],
            current_image=b.get("image", ""),
        )
        show_success("Bin updated.")
        return updated.get("bin", b)
    except APIError as e:
        show_error(str(e))
        return None


def items_in_bin_menu(cfg: dict, client: api_module.BinInventoryAPI, bin_data: dict) -> None:
    while True:
        try:
            data = client.get_items_by_bin(bin_data["id"])
            items = data.get("items", [])
        except APIError as e:
            show_error(str(e))
            return

        if items:
            _print_items_table(items)
        else:
            console.print(f"  [yellow]No items in '{bin_data['binName']}'.[/yellow]")

        choices = [
            questionary.Choice(f"[{i}]  {it['item']}", value=("open", it))
            for i, it in enumerate(items, 1)
        ] + [
            questionary.Separator(),
            questionary.Choice("+ Add Item to this Bin", value=("new", None)),
            questionary.Choice("← Back", value=("back", None)),
        ]

        result = sel(f"Items in '{bin_data['binName']}' ({len(items)}):", choices)
        if result is None:
            return
        action, payload = result

        if action == "back":
            return
        elif action == "new":
            create_item_view(cfg, client, preselect_bin=bin_data)
        elif action == "open":
            try:
                bins_data = client.get_bins_by_user(cfg["userId"])
                bins = bins_data.get("bins", [])
            except APIError:
                bins = []
            item_detail_menu(cfg, client, payload, bins)


# ── Items ─────────────────────────────────────────────────────────────────────

def _print_items_table(items: list) -> None:
    table = Table(box=box.ROUNDED, show_header=True, header_style="bold cyan", padding=(0, 1))
    table.add_column("#", style="dim", width=4)
    table.add_column("Name", min_width=22)
    table.add_column("Bin", min_width=16)
    table.add_column("Type", min_width=10)
    table.add_column("Qty", justify="right", width=5)
    table.add_column("Serial #", min_width=14)

    for i, it in enumerate(items, 1):
        table.add_row(
            str(i),
            it.get("item", ""),
            _bin_name_from_item(it),
            it.get("type", "") or "",
            str(it.get("quantity", "")) if it.get("quantity") is not None else "",
            it.get("serialNumber", "") or "",
        )
    console.print()
    console.print(table)


def all_items_menu(cfg: dict, client: api_module.BinInventoryAPI) -> None:
    while True:
        try:
            data = client.get_items_by_user(cfg["userId"])
            items = data.get("items", [])
        except APIError as e:
            show_error(str(e))
            return

        if not items:
            console.print("  [yellow]No items found.[/yellow]")
            ask("Press Enter to go back...")
            return

        choices = [
            {
                "name": (
                    it["item"]
                    + (f"  → {_bin_name_from_item(it)}" if _bin_name_from_item(it) else "")
                    + (f"  [{it['type']}]" if it.get("type") else "")
                    + (f"  qty:{it['quantity']}" if it.get("quantity") is not None else "")
                ),
                "value": ("open", it),
            }
            for it in items
        ] + [
            {"name": "+ New Item", "value": ("new", None)},
            {"name": "← Back",    "value": ("back", None)},
        ]

        result = _fuzzy_pick(f"My Items ({len(items)}):", choices)
        if result is None:
            return
        action, payload = result

        if action == "back":
            return
        elif action == "new":
            create_item_view(cfg, client)
        elif action == "open":
            try:
                bins_data = client.get_bins_by_user(cfg["userId"])
                bins = bins_data.get("bins", [])
            except APIError:
                bins = []
            item_detail_menu(cfg, client, payload, bins)


def item_detail_menu(
    cfg: dict,
    client: api_module.BinInventoryAPI,
    item_data: dict,
    bins: list,
) -> None:
    while True:
        it = item_data
        images = _item_images(it)
        prev_bin_name = _prev_bin_name_from_item(it)

        details = (
            f"[bold]{it.get('item', '')}[/bold]\n\n"
            f"  [dim]Description:[/dim]    {it.get('description', '') or '—'}\n"
            f"  [dim]Story / Notes:[/dim]  {it.get('story', '') or '—'}\n"
            f"  [dim]Type:[/dim]           {it.get('type', '') or '—'}\n"
            f"  [dim]Quantity:[/dim]       {it.get('quantity', '') if it.get('quantity') is not None else '—'}\n"
            f"  [dim]Bin:[/dim]            {_bin_name_from_item(it) or '—'}\n"
            f"  [dim]Previous Bin:[/dim]   {prev_bin_name or '—'}\n"
            f"  [dim]Serial #:[/dim]       {it.get('serialNumber', '') or '—'}\n"
            f"  [dim]Manufacturer:[/dim]   {it.get('manufacturer', '') or '—'}\n"
            f"  [dim]Purchased from:[/dim] {it.get('purchasedFrom', '') or '—'}\n"
            f"  [dim]Purchase date:[/dim]  {fmt_date(it.get('purchaseDate')) or '—'}\n"
            f"  [dim]Purchase price:[/dim] {it.get('purchasePrice', '') if it.get('purchasePrice') is not None else '—'}\n"
            f"  [dim]Date of mfg:[/dim]    {fmt_date(it.get('dateOfManufacture')) or '—'}\n"
            f"  [dim]Images:[/dim]         {len(images)} image(s)"
        )

        console.print()
        console.print(Panel(details, title="Item Details", border_style="cyan", padding=(0, 1)))

        if images:
            mode = cfg.get("image_mode", "none")
            if mode != "none":
                render_image(images[0], mode)
                if len(images) > 1:
                    console.print(f"  [dim]+ {len(images) - 1} more image(s) — URLs:[/dim]")
                    for url in images[1:]:
                        console.print(f"    {url}")
            else:
                console.print("  [dim]Image URLs:[/dim]")
                for url in images:
                    console.print(f"    {url}")

        action_choices = [
            ("Edit Item",   'e', "edit"),
            ("Delete Item", 'd', "delete"),
        ]
        if prev_bin_name:
            action_choices.append((f"Move back to '{prev_bin_name}'", 'm', "move_prev"))
        action_choices += [
            None,
            ("Back", 'b', "back"),
        ]

        action = shortcut_menu("Item actions:", action_choices)

        if action is None or action == "back":
            return
        elif action == "edit":
            updated = edit_item_view(cfg, client, it, bins)
            if updated:
                item_data = updated
        elif action == "delete":
            if confirm(f"Permanently delete '{it['item']}'?"):
                try:
                    client.delete_item(it["id"])
                    show_success("Item deleted.")
                    return
                except APIError as e:
                    show_error(str(e))
        elif action == "move_prev":
            prev_bin_id = _prev_bin_id_from_item(it)
            if prev_bin_id:
                try:
                    result = client.update_item(
                        item_id=it["id"],
                        item=it.get("item", ""),
                        bin_id=prev_bin_id,
                        user_id=cfg["userId"],
                        description=it.get("description", "") or "",
                        story=it.get("story", "") or "",
                        item_type=it.get("type", "") or "",
                        quantity=str(it.get("quantity", "")) if it.get("quantity") is not None else "",
                        purchase_date=fmt_date(it.get("purchaseDate")) or "",
                        purchased_from=it.get("purchasedFrom", "") or "",
                        manufacturer=it.get("manufacturer", "") or "",
                        date_of_manufacture=fmt_date(it.get("dateOfManufacture")) or "",
                        serial_number=it.get("serialNumber", "") or "",
                        purchase_price=str(it.get("purchasePrice", "")) if it.get("purchasePrice") is not None else "",
                        existing_images=images,
                    )
                    show_success(f"Moved back to '{prev_bin_name}'.")
                    item_data = result.get("thisItem", it)
                except APIError as e:
                    show_error(str(e))


def create_item_view(
    cfg: dict,
    client: api_module.BinInventoryAPI,
    preselect_bin: Optional[dict] = None,
) -> None:
    try:
        bins_data = client.get_bins_by_user(cfg["userId"])
        bins = bins_data.get("bins", [])
    except APIError as e:
        show_error(str(e))
        return

    if not bins:
        show_error("No bins found. Create a bin first.")
        return

    preselect_id = preselect_bin["id"] if preselect_bin else None
    result = run_item_form(bins=bins, preselect_bin_id=preselect_id)
    if result is None:
        return

    try:
        client.create_item(
            item=result["item"],
            bin_id=result["bin_id"],
            user_id=cfg["userId"],
            description=result["description"],
            story=result["story"],
            item_type=result["item_type"],
            quantity=result["quantity"],
            purchase_date=result["purchase_date"],
            purchased_from=result["purchased_from"],
            manufacturer=result["manufacturer"],
            date_of_manufacture=result["date_of_manufacture"],
            serial_number=result["serial_number"],
            purchase_price=result["purchase_price"],
            image_paths=result["new_image_paths"],
        )
        show_success(f"Item '{result['item']}' created.")
    except APIError as e:
        show_error(str(e))


def edit_item_view(
    cfg: dict,
    client: api_module.BinInventoryAPI,
    it: dict,
    bins: list,
) -> Optional[dict]:
    result = run_item_form(bins=bins, existing=it)
    if result is None:
        return None
    try:
        updated = client.update_item(
            item_id=it["id"],
            item=result["item"],
            bin_id=result["bin_id"],
            user_id=cfg["userId"],
            description=result["description"],
            story=result["story"],
            item_type=result["item_type"],
            quantity=result["quantity"],
            purchase_date=result["purchase_date"],
            purchased_from=result["purchased_from"],
            manufacturer=result["manufacturer"],
            date_of_manufacture=result["date_of_manufacture"],
            serial_number=result["serial_number"],
            purchase_price=result["purchase_price"],
            existing_images=result["existing_images"],
            new_image_paths=result["new_image_paths"],
        )
        show_success("Item updated.")
        return updated.get("thisItem", it)
    except APIError as e:
        show_error(str(e))
        return None


# ── Search ────────────────────────────────────────────────────────────────────

def search_menu(cfg: dict, client: api_module.BinInventoryAPI) -> None:
    while True:
        console.print()
        console.print(Panel("[bold]Search Items[/bold]", border_style="cyan", padding=(0, 2)))
        query = ask("Search term (or Enter to go back):")
        if not query:
            return

        try:
            data = client.search_items(query, cfg["userId"])
            items = data.get("items", [])
        except APIError:
            console.print("  [yellow]No results found.[/yellow]")
            continue

        if not items:
            console.print("  [yellow]No results found.[/yellow]")
            continue

        choices = [
            {
                "name": (
                    it["item"]
                    + (f"  → {_bin_name_from_item(it)}" if _bin_name_from_item(it) else "")
                    + (f"  [{it['type']}]" if it.get("type") else "")
                    + (f"  qty:{it['quantity']}" if it.get("quantity") is not None else "")
                ),
                "value": ("open", it),
            }
            for it in items
        ] + [
            {"name": "← New Search", "value": ("back", None)},
        ]

        result = _fuzzy_pick(f"Results for '{query}' ({len(items)}):", choices)
        if result is None:
            continue
        action, payload = result

        if action == "back":
            continue
        elif action == "open":
            try:
                bins_data = client.get_bins_by_user(cfg["userId"])
                bins = bins_data.get("bins", [])
            except APIError:
                bins = []
            item_detail_menu(cfg, client, payload, bins)


# ── Shared Bins ───────────────────────────────────────────────────────────────

def shared_bins_menu(cfg: dict, client: api_module.BinInventoryAPI) -> None:
    try:
        data = client.get_shared_bins(cfg["userId"])
        bins = data.get("bin", [])
    except APIError:
        console.print("  [yellow]No bins have been shared with you.[/yellow]")
        ask("Press Enter to continue...")
        return

    if not bins:
        console.print("  [yellow]No bins have been shared with you.[/yellow]")
        ask("Press Enter to continue...")
        return

    while True:
        table = Table(box=box.ROUNDED, show_header=True, header_style="bold cyan", padding=(0, 1))
        table.add_column("#", style="dim", width=4)
        table.add_column("Name", min_width=22)
        table.add_column("Owner", min_width=16)
        table.add_column("Location", min_width=14)
        table.add_column("Items", justify="right", width=6)

        for i, b in enumerate(bins, 1):
            owner = ""
            if isinstance(b.get("creator"), dict):
                owner = b["creator"].get("name") or b["creator"].get("email", "")
            table.add_row(
                str(i),
                b.get("binName", ""),
                owner,
                b.get("location", "") or "",
                str(len(b.get("items", []))),
            )

        console.print()
        console.print(table)

        choices = [
            questionary.Choice(f"[{i}]  {b['binName']}", value=("open", b))
            for i, b in enumerate(bins, 1)
        ] + [
            questionary.Separator(),
            questionary.Choice("← Back", value=("back", None)),
        ]

        result = sel(f"Shared Bins ({len(bins)}):", choices)
        if result is None:
            return
        action, payload = result

        if action == "back":
            return
        elif action == "open":
            shared_bin_items_view(cfg, client, payload)


def shared_bin_items_view(cfg: dict, client: api_module.BinInventoryAPI, bin_data: dict) -> None:
    try:
        data = client.get_items_by_bin(bin_data["id"])
        items = data.get("items", [])
    except APIError as e:
        show_error(str(e))
        return

    if not items:
        console.print(f"  [yellow]No items in '{bin_data['binName']}'.[/yellow]")
        ask("Press Enter to continue...")
        return

    while True:
        _print_items_table(items)

        choices = [
            questionary.Choice(f"[{i}]  {it['item']}", value=("open", it))
            for i, it in enumerate(items, 1)
        ] + [
            questionary.Separator(),
            questionary.Choice("← Back", value=("back", None)),
        ]

        result = sel(f"Items in '{bin_data['binName']}':", choices)
        if result is None:
            return
        action, payload = result

        if action == "back":
            return
        elif action == "open":
            item_detail_menu(cfg, client, payload, [])


# ── Profile ───────────────────────────────────────────────────────────────────

def profile_menu(cfg: dict, client: api_module.BinInventoryAPI) -> None:
    while True:
        try:
            data = client.get_user(cfg["userId"])
            user = data.get("user", {})
        except APIError as e:
            show_error(str(e))
            return

        details = (
            f"[bold]{user.get('name', '')}[/bold]\n\n"
            f"  [dim]Email:[/dim]         {user.get('email', '')}\n"
            f"  [dim]About:[/dim]         {user.get('about', '') or '—'}\n"
            f"  [dim]On users page:[/dim] {'[green]Yes[/green]' if user.get('showOnUsersPage') else 'No'}\n"
            f"  [dim]Bins:[/dim]          {len(user.get('bins', []))}\n"
            f"  [dim]Items:[/dim]         {len(user.get('items', []))}"
        )

        console.print()
        console.print(Panel(details, title="My Profile", border_style="cyan", padding=(0, 1)))

        action = shortcut_menu("Profile actions:", [
            ("Edit Profile", 'e', "edit"),
            None,
            ("Back",         'b', "back"),
        ])

        if action is None or action == "back":
            return
        elif action == "edit":
            edit_profile_view(cfg, client, user)


def edit_profile_view(cfg: dict, client: api_module.BinInventoryAPI, user: dict) -> None:
    console.print(Panel("[bold]Edit Profile[/bold]", border_style="cyan"))

    name = ask("Name:", default=user.get("name", ""))
    email = ask("Email:", default=user.get("email", ""))
    about = ask("About:", default=user.get("about", "") or "")
    show = confirm("Show profile on the users page?", default=bool(user.get("showOnUsersPage")))

    console.print("  [dim]Leave password blank to keep your current password.[/dim]")
    password = ask_password("New password (min 8 chars, or Enter to skip):")

    console.print(f"  [dim]Current image:[/dim] {user.get('image', '—')}")
    image_paths = ask_file_paths("New profile image path (or Enter to keep current):")

    try:
        client.update_user(
            user_id=cfg["userId"],
            name=name,
            email=email,
            about=about,
            password=password,
            show_on_users_page=show,
            image_path=image_paths[0] if image_paths else None,
            current_image=user.get("image", ""),
        )
        if email != cfg.get("email"):
            cfg["email"] = email
            config.save(cfg)
        show_success("Profile updated.")
    except APIError as e:
        show_error(str(e))


# ── Settings ──────────────────────────────────────────────────────────────────

def settings_menu(cfg: dict) -> None:
    current = cfg.get("image_mode", "none")
    console.print()
    console.print(Panel(
        f"[bold]Settings[/bold]\n\n"
        f"  [dim]Current image mode:[/dim] [cyan]{current}[/cyan]",
        border_style="cyan",
        padding=(0, 1),
    ))

    mode = shortcut_menu("Image display mode:", [
        ("No images  — fastest, works on any terminal",          'n', "none"),
        ("ANSI color blocks  — pixel-art look, color terminal",  'a', "ansi"),
        ("ASCII art  — monochrome, works everywhere",            's', "ascii"),  # aSCII
        None,
        ("Back (no change)",                                     'b', "back"),
    ])

    if mode is None or mode == "back":
        return

    cfg["image_mode"] = mode
    config.save(cfg)
    labels = {"none": "No images", "ansi": "ANSI color blocks", "ascii": "ASCII art"}
    show_success(f"Image mode set to: {labels[mode]}")
