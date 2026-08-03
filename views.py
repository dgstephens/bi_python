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
from rich import box

import config
import api as api_module
from api import APIError
from forms import run_bin_form, run_item_form
from images import render_image

console = Console()

# Retro color palette: dark blue bg / cyan labels / white values / yellow hotkeys
STYLE = questionary.Style([
    ("qmark",       "fg:#55ffff bold"),
    ("question",    "fg:#ffffff bold"),
    ("answer",      "fg:#ffff55 bold"),
    ("pointer",     "fg:#ffff55 bold"),
    ("highlighted", "fg:#ffff55 bold"),
    ("selected",    "fg:#55ffff"),
    ("separator",   "fg:#5555aa"),
    ("instruction", "fg:#5555aa"),
])


class NavigateTo(Exception):
    """Raised by shortcut_menu when a global nav key (1-4) is pressed."""
    def __init__(self, dest: str):
        self.dest = dest


# ── Display helpers ────────────────────────────────────────────────────────────

def fmt_date(date_str: Optional[str]) -> str:
    if not date_str:
        return ""
    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d")
    except Exception:
        return date_str[:10] if len(date_str) >= 10 else date_str


def _header(title: str = "") -> None:
    """Consistent full-width rule with app name and optional page title."""
    if title:
        console.rule(
            f"[bold cyan] BinInventory [/bold cyan][cyan]|[/cyan][bold white] {title} [/bold white]",
            style="cyan",
        )
    else:
        console.rule("[bold cyan] BinInventory [/bold cyan]", style="cyan")
    console.print()


def _field(label: str, value: str, width: int = 14) -> None:
    """Print one label : value row."""
    v = str(value) if value not in (None, "") else "—"
    console.print(f"  [cyan]{label.rjust(width)}[/cyan] : [white]{v}[/white]")


def show_error(msg: str) -> None:
    console.print()
    console.print(f"  [bold red][ ERROR ][/bold red] [red]{msg}[/red]")
    console.print()


def show_success(msg: str) -> None:
    console.print()
    console.print(f"  [bold green][  OK  ][/bold green] [green]{msg}[/green]")
    console.print()


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
    return questionary.select(prompt, choices=choices, style=STYLE).ask()


def _fuzzy_pick(prompt: str, choices: list):
    """Full list + type-to-filter + arrow keys. Returns value or None."""
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
    """Single-keypress menu.

    Items: list of (label, shortcut_char, value) or None for separator.
    Global nav keys always available: 1=Main 2=Bins 3=Items 4=Search.
    Raises NavigateTo for global keys; returns None for Esc/Ctrl-C.
    """
    key_map = {}

    console.print()
    if prompt:
        console.print(f"  [bold white]{prompt}[/bold white]")
        console.print()

    for item in items:
        if item is None:
            console.print("  [cyan]────────────────────────────────[/cyan]")
            continue
        label, shortcut, value = item
        key_map[shortcut.lower()] = value
        console.print(
            f"  [bold yellow]{escape('[' + shortcut.upper() + ']')}[/bold yellow]"
            f"  [white]{label}[/white]"
        )

    console.print()
    console.print("  [cyan]────────────────────────────────────────────────[/cyan]")
    console.print(
        "  [cyan][[/cyan][bold cyan]1[/bold cyan][cyan]][/cyan][dim] Main  [/dim]"
        "[cyan][[/cyan][bold cyan]2[/bold cyan][cyan]][/cyan][dim] Bins  [/dim]"
        "[cyan][[/cyan][bold cyan]3[/bold cyan][cyan]][/cyan][dim] Items  [/dim]"
        "[cyan][[/cyan][bold cyan]4[/bold cyan][cyan]][/cyan][dim] Search  [/dim]"
        "[cyan][[/cyan][bold cyan]Esc[/bold cyan][cyan]][/cyan][dim] Back[/dim]"
    )
    console.print()

    while True:
        key = readchar.readkey()
        if key in ('\x03', '\x1b'):
            return None
        if key == '1':
            raise NavigateTo("main")
        if key == '2':
            raise NavigateTo("bins")
        if key == '3':
            raise NavigateTo("items")
        if key == '4':
            raise NavigateTo("search")
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


# ── Item/bin data helpers ──────────────────────────────────────────────────────

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


# ── Auth ───────────────────────────────────────────────────────────────────────

def login_view(cfg: dict, client: api_module.BinInventoryAPI) -> dict:
    console.print()
    _header("Login")
    console.print("  [cyan]Personal inventory management[/cyan]")
    console.print()

    while True:
        action = sel("", [
            questionary.Choice("Login",   value="login"),
            questionary.Choice("Sign up", value="signup"),
            questionary.Separator(),
            questionary.Choice("Exit",    value="exit"),
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
                    "token":  result["token"],
                    "userId": result["userId"],
                    "email":  result["email"],
                })
                config.save(cfg)
                client.token = result["token"]
                show_success(f"Logged in as {email}")
                return cfg
            except APIError as e:
                show_error(str(e))

        elif action == "signup":
            name  = ask("Name:")
            email = ask("Email:")
            password = ask_password("Password (min 8 chars):")
            show = confirm("Show profile on the users page?")
            image_paths = ask_file_paths("Profile image path (or Enter to skip):")
            try:
                result = client.signup(
                    name=name, email=email, password=password,
                    show_on_users_page=show,
                    image_path=image_paths[0] if image_paths else None,
                )
                cfg.update({
                    "token":  result["token"],
                    "userId": result["userId"],
                    "email":  result["email"],
                })
                config.save(cfg)
                client.token = result["token"]
                show_success(f"Account created! Logged in as {email}")
                return cfg
            except APIError as e:
                show_error(str(e))


# ── Main menu ──────────────────────────────────────────────────────────────────

def main_menu(cfg: dict, client: api_module.BinInventoryAPI) -> None:
    """Top-level loop. Catches NavigateTo from any depth and re-routes."""
    dest = "main"
    while True:
        try:
            if dest == "bins":
                bins_menu(cfg, client)
                dest = "main"
            elif dest == "items":
                all_items_menu(cfg, client)
                dest = "main"
            elif dest == "search":
                search_menu(cfg, client)
                dest = "main"
            else:
                dest = _main_dispatch(cfg, client)
        except NavigateTo as e:
            dest = e.dest
        except KeyboardInterrupt:
            print("\nBye!")
            sys.exit(0)


def _main_dispatch(cfg: dict, client: api_module.BinInventoryAPI) -> str:
    """Show the main menu once, dispatch selection, return 'main'."""
    try:
        count_data = client.get_item_count(cfg["userId"])
        item_count = count_data.get("number", "?")
    except APIError:
        item_count = "?"

    console.print()
    _header()
    console.print(
        f"  [cyan]User[/cyan]  : [white]{cfg.get('email', '')}[/white]   "
        f"[cyan]Items[/cyan] : [white]{item_count}[/white]"
    )
    console.print()

    mode = cfg.get("image_mode", "none")
    mode_label = {"none": "No images", "ansi": "ANSI color", "ascii": "ASCII art"}.get(mode, mode)

    action = shortcut_menu("", [
        ("My Bins",                       'b', "bins"),
        ("My Items",                      'i', "items"),
        ("Search Items",                  's', "search"),
        ("Shared Bins",                   'h', "shared"),
        ("My Profile",                    'p', "profile"),
        (f"Settings  [{mode_label}]",     't', "settings"),
        None,
        ("Logout",                        'l', "logout"),
        ("Exit",                          'x', "exit"),
    ])

    if action is None or action == "exit":
        sys.exit(0)
    elif action == "logout":
        config.clear_auth(cfg)
        client.token = None
        console.print("  [cyan]Logged out.[/cyan]")
        login_view(cfg, client)
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

    return "main"


# ── Bins ───────────────────────────────────────────────────────────────────────

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
                    + (f"  {b['type']}" if b.get("type") else "")
                    + f"  ({len(b.get('items', []))} items)"
                ),
                "value": ("open", b),
            }
            for b in bins
        ] + [
            {"name": "+ New Bin", "value": ("new",  None)},
            {"name": "<- Back",   "value": ("back", None)},
        ]

        console.print()
        _header("My Bins")
        result = _fuzzy_pick(f"{len(bins)} bin(s) — type to filter, arrows to scroll:", choices)
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
        console.print()
        _header(f"Bin : {b.get('binName', '')}")

        _field("Name",        b.get("binName", ""))
        _field("Description", b.get("description", "") or "")
        _field("Location",    b.get("location", "") or "")
        _field("Type",        b.get("type", "") or "")
        _field("Public",      "Yes" if b.get("public") else "No")
        _field("Shared with", ", ".join(b.get("sharedWith", [])) or "")
        _field("Items",       str(len(b.get("items", []))))
        console.print()

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

        choices = [
            {
                "name": (
                    it["item"]
                    + (f"  [{it['type']}]" if it.get("type") else "")
                    + (f"  qty:{it['quantity']}" if it.get("quantity") is not None else "")
                ),
                "value": ("open", it),
            }
            for it in items
        ] + [
            {"name": "+ Add Item to this Bin", "value": ("new",  None)},
            {"name": "<- Back",                "value": ("back", None)},
        ]

        console.print()
        _header(f"Items in : {bin_data['binName']}")
        if not items:
            console.print(f"  [yellow]No items in this bin.[/yellow]")
            console.print()

        result = _fuzzy_pick(
            f"{len(items)} item(s) — type to filter, arrows to scroll:",
            choices,
        )
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


# ── Items ──────────────────────────────────────────────────────────────────────

def all_items_menu(cfg: dict, client: api_module.BinInventoryAPI) -> None:
    while True:
        try:
            data = client.get_items_by_user(cfg["userId"])
            items = data.get("items", [])
        except APIError as e:
            show_error(str(e))
            return

        if not items:
            console.print()
            _header("My Items")
            console.print("  [yellow]No items found.[/yellow]")
            ask("  Press Enter to go back...")
            return

        choices = [
            {
                "name": (
                    it["item"]
                    + (f"  -> {_bin_name_from_item(it)}" if _bin_name_from_item(it) else "")
                    + (f"  [{it['type']}]" if it.get("type") else "")
                    + (f"  qty:{it['quantity']}" if it.get("quantity") is not None else "")
                ),
                "value": ("open", it),
            }
            for it in items
        ] + [
            {"name": "+ New Item", "value": ("new",  None)},
            {"name": "<- Back",    "value": ("back", None)},
        ]

        console.print()
        _header("My Items")
        result = _fuzzy_pick(f"{len(items)} item(s) — type to filter, arrows to scroll:", choices)
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

        console.print()
        _header(f"Item : {it.get('item', '')}")

        _field("Name",         it.get("item", ""))
        _field("Bin",          _bin_name_from_item(it))
        _field("Prev. bin",    prev_bin_name)
        _field("Description",  it.get("description", "") or "")
        _field("Story",        it.get("story", "") or "")
        _field("Type",         it.get("type", "") or "")
        _field("Quantity",     str(it.get("quantity", "")) if it.get("quantity") is not None else "")
        _field("Serial #",     it.get("serialNumber", "") or "")
        _field("Manufacturer", it.get("manufacturer", "") or "")
        _field("Purch. from",  it.get("purchasedFrom", "") or "")
        _field("Purch. date",  fmt_date(it.get("purchaseDate")) or "")
        _field("Price",        str(it.get("purchasePrice", "")) if it.get("purchasePrice") is not None else "")
        _field("Mfr. date",    fmt_date(it.get("dateOfManufacture")) or "")
        _field("Images",       f"{len(images)} image(s)")
        console.print()

        if images:
            mode = cfg.get("image_mode", "none")
            if mode != "none":
                render_image(images[0], mode)
                if len(images) > 1:
                    console.print(f"  [cyan]  + {len(images) - 1} more image(s)[/cyan]")
            else:
                for url in images:
                    console.print(f"  [dim]{url}[/dim]")

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


# ── Search ─────────────────────────────────────────────────────────────────────

def search_menu(cfg: dict, client: api_module.BinInventoryAPI) -> None:
    while True:
        console.print()
        _header("Search Items")
        query = ask("  Search term (Enter to go back):")
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
                    + (f"  -> {_bin_name_from_item(it)}" if _bin_name_from_item(it) else "")
                    + (f"  [{it['type']}]" if it.get("type") else "")
                    + (f"  qty:{it['quantity']}" if it.get("quantity") is not None else "")
                ),
                "value": ("open", it),
            }
            for it in items
        ] + [
            {"name": "<- New Search", "value": ("back", None)},
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


# ── Shared Bins ────────────────────────────────────────────────────────────────

def shared_bins_menu(cfg: dict, client: api_module.BinInventoryAPI) -> None:
    try:
        data = client.get_shared_bins(cfg["userId"])
        bins = data.get("bin", [])
    except APIError:
        bins = []

    if not bins:
        console.print()
        _header("Shared Bins")
        console.print("  [yellow]No bins have been shared with you.[/yellow]")
        ask("  Press Enter to continue...")
        return

    while True:
        choices = [
            {
                "name": (
                    b["binName"]
                    + (f"  [{b.get('location', '')}]" if b.get("location") else "")
                    + f"  ({len(b.get('items', []))} items)"
                ),
                "value": ("open", b),
            }
            for b in bins
        ] + [
            {"name": "<- Back", "value": ("back", None)},
        ]

        console.print()
        _header("Shared Bins")
        result = _fuzzy_pick(f"{len(bins)} shared bin(s):", choices)
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
        ask("  Press Enter to continue...")
        return

    while True:
        choices = [
            {
                "name": (
                    it["item"]
                    + (f"  [{it['type']}]" if it.get("type") else "")
                ),
                "value": ("open", it),
            }
            for it in items
        ] + [
            {"name": "<- Back", "value": ("back", None)},
        ]

        console.print()
        _header(f"Shared : {bin_data['binName']}")
        result = _fuzzy_pick(f"{len(items)} item(s):", choices)
        if result is None:
            return
        action, payload = result

        if action == "back":
            return
        elif action == "open":
            item_detail_menu(cfg, client, payload, [])


# ── Profile ────────────────────────────────────────────────────────────────────

def profile_menu(cfg: dict, client: api_module.BinInventoryAPI) -> None:
    while True:
        try:
            data = client.get_user(cfg["userId"])
            user = data.get("user", {})
        except APIError as e:
            show_error(str(e))
            return

        console.print()
        _header("My Profile")
        _field("Name",         user.get("name", ""))
        _field("Email",        user.get("email", ""))
        _field("About",        user.get("about", "") or "")
        _field("On users page", "Yes" if user.get("showOnUsersPage") else "No")
        _field("Bins",         str(len(user.get("bins", []))))
        _field("Items",        str(len(user.get("items", []))))
        console.print()

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
    console.print()
    _header("Edit Profile")

    name  = ask("Name:", default=user.get("name", ""))
    email = ask("Email:", default=user.get("email", ""))
    about = ask("About:", default=user.get("about", "") or "")
    show  = confirm("Show profile on the users page?", default=bool(user.get("showOnUsersPage")))

    console.print("  [dim]Leave password blank to keep your current password.[/dim]")
    password = ask_password("New password (min 8 chars, or Enter to skip):")

    console.print(f"  [cyan]Current image[/cyan] : [dim]{user.get('image', '—')}[/dim]")
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


# ── Settings ───────────────────────────────────────────────────────────────────

def settings_menu(cfg: dict) -> None:
    current = cfg.get("image_mode", "none")
    console.print()
    _header("Settings")
    _field("Image mode", current)
    console.print()

    mode = shortcut_menu("Image display mode:", [
        ("No images  — fastest, works everywhere",           'n', "none"),
        ("ANSI color blocks  — pixel-art, color terminal",   'a', "ansi"),
        ("ASCII art  — monochrome, works everywhere",        's', "ascii"),
        None,
        ("Back (no change)",                                 'b', "back"),
    ])

    if mode is None or mode == "back":
        return

    cfg["image_mode"] = mode
    config.save(cfg)
    labels = {"none": "No images", "ansi": "ANSI color blocks", "ascii": "ASCII art"}
    show_success(f"Image mode set to: {labels[mode]}")
