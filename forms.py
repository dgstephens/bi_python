"""Textual-based forms for BinInventory CLI.

Public API
----------
run_bin_form(existing=None)                                         -> Optional[dict]
run_item_form(bins, existing=None, preselect_bin_id=None,
              image_mode="none")                                    -> Optional[dict]
run_search_form()                                                   -> Optional[str]
run_profile_form(user)                                              -> Optional[dict]
"""

import asyncio
from datetime import datetime
from io import BytesIO
from typing import List, Optional

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, ScrollableContainer
from textual.screen import Screen
from textual.widgets import DataTable, Input, Label, Select, Static, Switch, TextArea


# ── Retro widget subclasses ─────────────────────────────────────────────────────
# In Textual 8.x, widget on_mount fires BEFORE App.on_mount, so any inline
# styles we set get overwritten when self.dark=True triggers a CSS re-evaluation.
# call_after_refresh() defers style application until after that settles.

class RetroInput(Input):
    def on_mount(self) -> None:
        try:
            self.styles.border = ("none", "transparent")
        except Exception:
            pass
        self.app.call_after_refresh(self._init_color)

    def _init_color(self) -> None:
        self.styles.color = "white"

    def on_focus(self) -> None:
        self.styles.color = "#ffff55"

    def on_blur(self) -> None:
        self.styles.color = "white"


class RetroTextArea(TextArea):
    """Multi-line text area styled to match the retro theme."""

    def on_mount(self) -> None:
        try:
            self.styles.border = ("none", "transparent")
        except Exception:
            pass
        self.app.call_after_refresh(self._init_color)

    def _init_color(self) -> None:
        self.styles.color = "white"

    def on_focus(self) -> None:
        self.styles.color = "#ffff55"

    def on_blur(self) -> None:
        self.styles.color = "white"


class RetroSelect(Select):
    def on_mount(self) -> None:
        self.app.call_after_refresh(self._init_color)

    def _init_color(self) -> None:
        self.styles.color = "white"
        # Force color on inner widgets (SelectCurrent, its Static child, etc.)
        try:
            for child in self.query("*"):
                child.styles.color = "white"
        except Exception:
            pass

    def on_focus(self) -> None:
        self.styles.color = "#ffff55"
        try:
            for child in self.query("*"):
                child.styles.color = "#ffff55"
        except Exception:
            pass

    def on_blur(self) -> None:
        self.styles.color = "white"
        try:
            for child in self.query("*"):
                child.styles.color = "white"
        except Exception:
            pass


class RetroSwitch(Switch):
    def on_mount(self) -> None:
        try:
            self.styles.border = ("none", "transparent")
        except Exception:
            pass


class _ImgCountWidget(Static):
    """Focusable widget showing image count; Enter opens the image manager."""
    can_focus = True

    def on_key(self, event) -> None:
        if event.key == "enter":
            event.stop()
            self.app.action_manage_images()

    def on_focus(self) -> None:
        self.styles.color = "#ffff55"

    def on_blur(self) -> None:
        self.styles.color = "#55ffff"


# ── Shared helpers ─────────────────────────────────────────────────────────────

def _fmt_date(date_str: Optional[str]) -> str:
    if not date_str:
        return ""
    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d")
    except Exception:
        return date_str[:10] if len(date_str) >= 10 else date_str


def _item_images(it: dict) -> List[str]:
    imgs = it.get("images") or []
    if not imgs and it.get("image"):
        imgs = [it["image"]]
    return [u for u in imgs if u]


def _bin_id_from_item(item: dict) -> str:
    bid = item.get("binId")
    if isinstance(bid, dict):
        return bid.get("id", "")
    return bid or ""


def _image_to_renderable(url: str, mode: str):
    """Download *url* and return a Rich renderable suitable for a Static widget.

    Returns a Pixels object (ansi), an ASCII string (ascii), or None.
    """
    if not url or mode == "none":
        return None
    try:
        import requests
        from PIL import Image
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        img = Image.open(BytesIO(resp.content)).convert("RGB")
        w = 60
        aspect = img.height / img.width

        if mode == "ansi":
            from rich_pixels import Pixels
            h = max(1, int(w * aspect * 1.0))
            return Pixels.from_image(img, resize=(w, h))

        elif mode == "ascii":
            import ascii_magic
            if hasattr(ascii_magic, "AsciiArt"):
                art = ascii_magic.AsciiArt.from_pillow_image(img)
                return art.to_ascii(columns=w)
            else:
                return ascii_magic.from_pillow_image(img)

    except Exception:
        return None


# ── Shared CSS ─────────────────────────────────────────────────────────────────
# Using App.CSS (not DEFAULT_CSS) so our rules have higher priority than
# widget-level DEFAULT_CSS, matching Textual's documented precedence order.

_CSS = """
Screen {
    background: #000080;
    color: #ffffff;
    overflow: auto;
}
#form-title {
    background: #008888;
    color: #000000;
    height: 1;
    padding: 0 1;
    text-style: bold;
}
#form-hint {
    background: #000080;
    color: #5555aa;
    height: 1;
    padding: 0 1;
    border-bottom: solid #005588;
}
#fields {
    padding: 1 1;
    background: #000080;
    height: auto;
}
.row {
    height: 1;
    margin-bottom: 1;
    background: #000080;
    align: left middle;
}
.multirow {
    height: 6;
    margin-bottom: 1;
    background: #000080;
    align: left top;
}
.lbl {
    width: 18;
    height: 1;
    content-align: right middle;
    color: #55ffff;
    background: #000080;
}
.lbl-top {
    width: 18;
    height: 1;
    content-align: right top;
    color: #55ffff;
    background: #000080;
    padding-top: 0;
}
.lbl-req {
    color: #ffff55;
    text-style: bold;
}
Input {
    width: 1fr;
    height: 1;
    border: none;
    padding: 0 1;
    color: white;
    background: $surface;
}
Input > .input--value {
    color: white;
}
Input > .input--placeholder {
    color: #5555aa;
}
TextArea {
    width: 1fr;
    height: 5;
    border: none;
    padding: 0 1;
    color: white;
    background: $surface;
}
Select {
    width: 1fr;
    border: none;
    color: white;
}
SelectCurrent {
    color: white;
    background: $surface;
    border: none;
}
SelectCurrent > Static {
    color: white;
}
Select > .select--button {
    color: white;
    background: $surface;
    border: none;
}
Switch {
    background: #000080;
    height: 1;
    border: none;
    color: #55ffff;
}
Switch.-on {
    color: #ffff55;
}
Switch:focus {
    border: none;
    background: #000060;
}
.info-row {
    width: 1fr;
    height: 1;
    color: #55ffff;
    background: #000080;
    content-align: left middle;
    padding: 0 1;
}
.info-row:focus {
    color: #ffff55;
    background: #000060;
}
.curr-img {
    width: 1fr;
    height: 1;
    color: #5555aa;
    background: #000080;
    content-align: left middle;
    padding: 0 1;
}
.toggle-hint {
    width: 1fr;
    height: 1;
    color: #5555aa;
    background: #000080;
    content-align: left middle;
    padding: 0 1;
}
#img-note {
    color: #5555aa;
    height: 1;
    width: 1fr;
    content-align: left middle;
    background: #000080;
    padding-left: 1;
}
#img-preview {
    height: 16;
    width: 1fr;
    background: #000030;
    color: #888888;
    overflow: hidden;
    padding: 0 1;
    border-bottom: solid #005588;
}
#footer {
    height: 2;
    background: #000080;
    border-top: solid #005588;
    padding: 0 2;
    align: left middle;
}
DataTable {
    height: 1fr;
    margin: 1 1;
    background: #000050;
    border: none;
}
DataTable > .datatable--cursor {
    background: #000068;
    color: #ffff55;
}
"""


# ── Image manager screen ────────────────────────────────────────────────────────

class _ImageManagerScreen(Screen):
    BINDINGS = [
        Binding("escape", "done", "Done"),
        Binding("d", "delete_selected", "Delete"),
    ]
    CSS = _CSS

    def __init__(self, images: List[str], image_mode: str = "none") -> None:
        super().__init__()
        self._images = list(images)
        self._image_mode = image_mode

    def compose(self) -> ComposeResult:
        yield Static("", id="form-title")
        yield Static("↑↓: select   D: delete   Esc: done", id="form-hint")
        yield Static("[dim]Select an image to preview[/dim]", id="img-preview")
        yield DataTable(id="img-tbl", cursor_type="row", show_header=False)
        yield Static(
            "  [bold cyan]↑↓[/bold cyan]  Navigate    "
            "[bold cyan]D[/bold cyan]  Delete selected    "
            "[bold cyan]Esc[/bold cyan]  Done",
            id="footer",
        )

    def on_mount(self) -> None:
        self.app.dark = True
        tbl = self.query_one(DataTable)
        tbl.add_column("Image", width=80)
        self._rebuild()

    def _rebuild(self) -> None:
        tbl = self.query_one(DataTable)
        tbl.clear()
        for url in self._images:
            tbl.add_row(url.split("/")[-1])
        n = len(self._images)
        self.query_one("#form-title", Static).update(
            f"BinInventory  --  Manage Images  ({n} image{'s' if n != 1 else ''})"
        )

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        idx = event.cursor_row
        if 0 <= idx < len(self._images):
            url = self._images[idx]
            preview = self.query_one("#img-preview", Static)
            preview.update("[dim]Loading...[/dim]")
            self.run_worker(self._fetch_preview(url), exclusive=True)

    async def _fetch_preview(self, url: str) -> None:
        loop = asyncio.get_event_loop()
        renderable = await loop.run_in_executor(None, _image_to_renderable, url, self._image_mode)
        try:
            preview = self.query_one("#img-preview", Static)
            preview.update(renderable if renderable is not None else "[dim](no preview available)[/dim]")
        except Exception:
            pass

    def action_delete_selected(self) -> None:
        tbl = self.query_one(DataTable)
        idx = tbl.cursor_row
        if self._images and 0 <= idx < len(self._images):
            self._images.pop(idx)
            self._rebuild()
            self.query_one("#img-preview", Static).update("[dim]Select an image to preview[/dim]")
            if self._images:
                try:
                    tbl.move_cursor(row=min(idx, len(self._images) - 1))
                except Exception:
                    pass

    def action_done(self) -> None:
        self.app._remaining_images = list(self._images)
        try:
            n = len(self._images)
            self.app.query_one("#img-count", _ImgCountWidget).update(
                f"{n} image{'s' if n != 1 else ''}  —  Press [bold cyan]Enter[/bold cyan]"
                if n > 0 else "No images remaining"
            )
        except Exception:
            pass
        self.app.pop_screen()


# ── Bin form ───────────────────────────────────────────────────────────────────

class _BinFormApp(App):
    BINDINGS = [
        Binding("ctrl+s", "save", "Save"),
        Binding("escape", "cancel", "Cancel"),
    ]
    CSS = _CSS

    def __init__(self, existing: Optional[dict] = None):
        super().__init__()
        self._existing = existing or {}

    def compose(self) -> ComposeResult:
        b = self._existing
        title = f"BinInventory  --  {'Edit Bin: ' + b['binName'] if b else 'New Bin'}"
        yield Static(title, id="form-title")
        yield Static("Tab/Shift+Tab: move between fields", id="form-hint")
        current_img = b.get("image", "")
        with ScrollableContainer(id="fields"):
            with Horizontal(classes="row"):
                yield Label("Name :", classes="lbl lbl-req")
                yield RetroInput(value=b.get("binName", ""), id="bin_name", placeholder="required")
            with Horizontal(classes="row"):
                yield Label("Description :", classes="lbl")
                yield RetroInput(value=b.get("description", "") or "", id="description")
            with Horizontal(classes="row"):
                yield Label("Location :", classes="lbl")
                yield RetroInput(value=b.get("location", "") or "", id="location")
            with Horizontal(classes="row"):
                yield Label("Type :", classes="lbl")
                yield RetroInput(value=b.get("type", "") or "", id="bin_type")
            with Horizontal(classes="row"):
                yield Label("Public :", classes="lbl")
                yield RetroSwitch(value=bool(b.get("public", False)), id="public")
                yield Static("  Space to toggle ON / OFF", classes="toggle-hint")
            with Horizontal(classes="row"):
                yield Label("Share with :", classes="lbl")
                yield RetroInput(
                    value=" ".join(b.get("sharedWith", [])),
                    id="sw_emails",
                    placeholder="space-separated emails",
                )
            if current_img:
                img_name = current_img.split("/")[-1]
                with Horizontal(classes="row"):
                    yield Label("Curr. img :", classes="lbl")
                    yield Static(img_name, classes="curr-img")
            with Horizontal(classes="row"):
                yield Label("New img :", classes="lbl")
                ph = "file path (leave blank to keep current)" if current_img else "file path or leave blank"
                yield RetroInput(value="", id="image_path", placeholder=ph)
        yield Static(
            "  [bold cyan]Ctrl+S[/bold cyan]  Save       "
            "[bold cyan]Esc[/bold cyan]  Cancel",
            id="footer",
        )

    def on_mount(self) -> None:
        self.dark = True
        self.query_one("#bin_name", Input).focus()

    def action_save(self) -> None:
        bin_name = self.query_one("#bin_name", Input).value.strip()
        if not bin_name:
            self.query_one("#bin_name", Input).focus()
            self.notify("Name is required", severity="error")
            return
        self.exit({
            "bin_name": bin_name,
            "description": self.query_one("#description", Input).value.strip(),
            "location": self.query_one("#location", Input).value.strip(),
            "bin_type": self.query_one("#bin_type", Input).value.strip(),
            "public": self.query_one("#public", RetroSwitch).value,
            "sw_emails": self.query_one("#sw_emails", Input).value.strip(),
            "image_path": self.query_one("#image_path", Input).value.strip() or None,
        })

    def action_cancel(self) -> None:
        self.exit(None)


# ── Item form ──────────────────────────────────────────────────────────────────

class _ItemFormApp(App):
    BINDINGS = [
        Binding("ctrl+s", "save", "Save"),
        Binding("escape", "cancel", "Cancel"),
    ]
    CSS = _CSS

    def __init__(
        self,
        bins: list,
        existing: Optional[dict] = None,
        preselect_bin_id: Optional[str] = None,
        image_mode: str = "none",
    ):
        super().__init__()
        self._bins = bins
        self._existing = existing or {}
        self._preselect_bin_id = preselect_bin_id
        self._image_mode = image_mode
        self._remaining_images: List[str] = list(_item_images(self._existing))

    def compose(self) -> ComposeResult:
        it = self._existing
        title = f"BinInventory  --  {'Edit Item: ' + it['item'] if it else 'New Item'}"
        yield Static(title, id="form-title")
        yield Static("Tab/Shift+Tab: move between fields   Ctrl+S: save   Esc: cancel", id="form-hint")

        current_bin_id = _bin_id_from_item(it) or self._preselect_bin_id
        bin_options = [(b["binName"], b["id"]) for b in self._bins]
        selected_bin = current_bin_id if current_bin_id else (bin_options[0][1] if bin_options else None)

        with ScrollableContainer(id="fields"):
            with Horizontal(classes="row"):
                yield Label("Name :", classes="lbl lbl-req")
                yield RetroInput(value=it.get("item", ""), id="item_name", placeholder="required")
            with Horizontal(classes="row"):
                yield Label("Bin :", classes="lbl lbl-req")
                yield RetroSelect(options=bin_options, value=selected_bin, id="bin_id", allow_blank=False)
            with Horizontal(classes="multirow"):
                yield Label("Description :", classes="lbl lbl-top")
                yield RetroTextArea(it.get("description", "") or "", id="description", tab_behavior="focus")
            with Horizontal(classes="multirow"):
                yield Label("Story :", classes="lbl lbl-top")
                yield RetroTextArea(it.get("story", "") or "", id="story", tab_behavior="focus")
            with Horizontal(classes="row"):
                yield Label("Type :", classes="lbl")
                yield RetroInput(value=it.get("type", "") or "", id="item_type")
            with Horizontal(classes="row"):
                yield Label("Quantity :", classes="lbl")
                qty = str(it.get("quantity", "")) if it.get("quantity") is not None else ""
                yield RetroInput(value=qty, id="quantity")
            with Horizontal(classes="row"):
                yield Label("Purch. date :", classes="lbl")
                yield RetroInput(
                    value=_fmt_date(it.get("purchaseDate")),
                    id="purchase_date",
                    placeholder="YYYY-MM-DD",
                )
            with Horizontal(classes="row"):
                yield Label("Purch. from :", classes="lbl")
                yield RetroInput(value=it.get("purchasedFrom", "") or "", id="purchased_from")
            with Horizontal(classes="row"):
                yield Label("Mfr. :", classes="lbl")
                yield RetroInput(value=it.get("manufacturer", "") or "", id="manufacturer")
            with Horizontal(classes="row"):
                yield Label("Mfr. date :", classes="lbl")
                yield RetroInput(
                    value=_fmt_date(it.get("dateOfManufacture")),
                    id="date_of_manufacture",
                    placeholder="YYYY-MM-DD",
                )
            with Horizontal(classes="row"):
                yield Label("Serial # :", classes="lbl")
                yield RetroInput(value=it.get("serialNumber", "") or "", id="serial_number")
            with Horizontal(classes="row"):
                yield Label("Price :", classes="lbl")
                price = str(it.get("purchasePrice", "")) if it.get("purchasePrice") is not None else ""
                yield RetroInput(value=price, id="purchase_price")
            if self._remaining_images:
                n = len(self._remaining_images)
                with Horizontal(classes="row"):
                    yield Label("Exist. imgs :", classes="lbl")
                    yield _ImgCountWidget(
                        f"{n} image{'s' if n != 1 else ''}  —  Press [bold cyan]Enter[/bold cyan]",
                        id="img-count",
                        classes="info-row",
                    )
            with Horizontal(classes="row"):
                yield Label("New images :", classes="lbl")
                yield RetroInput(value="", id="new_images", placeholder="comma-separated file paths")
        yield Static(
            "  [bold cyan]Ctrl+S[/bold cyan]  Save       "
            "[bold cyan]Esc[/bold cyan]  Cancel",
            id="footer",
        )

    def on_mount(self) -> None:
        self.dark = True
        self.query_one("#item_name", Input).focus()

    def action_manage_images(self) -> None:
        if not self._remaining_images:
            self.notify("No existing images to manage.", severity="warning")
            return
        self.push_screen(_ImageManagerScreen(self._remaining_images, image_mode=self._image_mode))

    def action_save(self) -> None:
        item_name = self.query_one("#item_name", Input).value.strip()
        if not item_name:
            self.query_one("#item_name", Input).focus()
            self.notify("Name is required", severity="error")
            return

        bin_sel = self.query_one("#bin_id", Select)
        bin_id = bin_sel.value
        if bin_id is Select.BLANK or not bin_id:
            self.notify("Please select a bin", severity="error")
            return

        new_raw = ""
        try:
            new_raw = self.query_one("#new_images", Input).value.strip()
        except Exception:
            pass
        new_paths = [p.strip() for p in new_raw.split(",") if p.strip()]

        self.exit({
            "item": item_name,
            "bin_id": bin_id,
            "description": self.query_one("#description", TextArea).text.strip(),
            "story": self.query_one("#story", TextArea).text.strip(),
            "item_type": self.query_one("#item_type", Input).value.strip(),
            "quantity": self.query_one("#quantity", Input).value.strip(),
            "purchase_date": self.query_one("#purchase_date", Input).value.strip(),
            "purchased_from": self.query_one("#purchased_from", Input).value.strip(),
            "manufacturer": self.query_one("#manufacturer", Input).value.strip(),
            "date_of_manufacture": self.query_one("#date_of_manufacture", Input).value.strip(),
            "serial_number": self.query_one("#serial_number", Input).value.strip(),
            "purchase_price": self.query_one("#purchase_price", Input).value.strip(),
            "existing_images": self._remaining_images,
            "new_image_paths": new_paths or None,
        })

    def action_cancel(self) -> None:
        self.exit(None)


# ── Profile form ───────────────────────────────────────────────────────────────

class _ProfileFormApp(App):
    BINDINGS = [
        Binding("ctrl+s", "save", "Save"),
        Binding("escape", "cancel", "Cancel"),
    ]
    CSS = _CSS

    def __init__(self, user: dict):
        super().__init__()
        self._user = user

    def compose(self) -> ComposeResult:
        yield Static("BinInventory  --  Edit Profile", id="form-title")
        yield Static("Tab/Shift+Tab: move between fields", id="form-hint")
        u = self._user
        with ScrollableContainer(id="fields"):
            with Horizontal(classes="row"):
                yield Label("Name :", classes="lbl lbl-req")
                yield RetroInput(value=u.get("name", "") or "", id="name")
            with Horizontal(classes="row"):
                yield Label("Email :", classes="lbl lbl-req")
                yield RetroInput(value=u.get("email", "") or "", id="email")
            with Horizontal(classes="row"):
                yield Label("About :", classes="lbl")
                yield RetroInput(value=u.get("about", "") or "", id="about")
            with Horizontal(classes="row"):
                yield Label("Display on Users Page :", classes="lbl")
                yield RetroSwitch(value=bool(u.get("showOnUsersPage", False)), id="show_on_users")
                yield Static("  Space to toggle ON / OFF", classes="toggle-hint")
            with Horizontal(classes="row"):
                yield Label("New password :", classes="lbl")
                yield RetroInput(
                    value="", id="password", password=True,
                    placeholder="leave blank to keep current",
                )
            if u.get("image"):
                img_name = u["image"].split("/")[-1]
                with Horizontal(classes="row"):
                    yield Label("Curr. img :", classes="lbl")
                    yield Static(img_name, classes="curr-img")
            with Horizontal(classes="row"):
                yield Label("New img :", classes="lbl")
                ph = "file path (leave blank to keep current)" if u.get("image") else "file path or leave blank"
                yield RetroInput(value="", id="image_path", placeholder=ph)
        yield Static(
            "  [bold cyan]Ctrl+S[/bold cyan]  Save       "
            "[bold cyan]Esc[/bold cyan]  Cancel",
            id="footer",
        )

    def on_mount(self) -> None:
        self.dark = True
        self.query_one("#name", Input).focus()

    def action_save(self) -> None:
        name = self.query_one("#name", Input).value.strip()
        email = self.query_one("#email", Input).value.strip()
        if not name or not email:
            self.notify("Name and email are required", severity="error")
            return
        self.exit({
            "name": name,
            "email": email,
            "about": self.query_one("#about", Input).value.strip(),
            "show_on_users_page": self.query_one("#show_on_users", RetroSwitch).value,
            "password": self.query_one("#password", Input).value,
            "image_path": self.query_one("#image_path", Input).value.strip() or None,
        })

    def action_cancel(self) -> None:
        self.exit(None)


# ── Search form ────────────────────────────────────────────────────────────────

class _SearchFormApp(App):
    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
    ]
    CSS = _CSS

    def compose(self) -> ComposeResult:
        yield Static("BinInventory  --  Search Items", id="form-title")
        yield Static("Enter: search   Esc: back", id="form-hint")
        with ScrollableContainer(id="fields"):
            with Horizontal(classes="row"):
                yield Label("Search :", classes="lbl lbl-req")
                yield RetroInput(id="query", placeholder="type to search...")
        yield Static(
            "  [bold cyan]Enter[/bold cyan]  Search       "
            "[bold cyan]Esc[/bold cyan]  Back",
            id="footer",
        )

    def on_mount(self) -> None:
        self.dark = True
        self.query_one("#query", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        query = event.value.strip()
        self.exit(query if query else None)

    def action_cancel(self) -> None:
        self.exit(None)


# ── Public API ─────────────────────────────────────────────────────────────────

def run_bin_form(existing: Optional[dict] = None) -> Optional[dict]:
    return _BinFormApp(existing=existing).run()


def run_item_form(
    bins: list,
    existing: Optional[dict] = None,
    preselect_bin_id: Optional[str] = None,
    image_mode: str = "none",
) -> Optional[dict]:
    return _ItemFormApp(
        bins=bins,
        existing=existing,
        preselect_bin_id=preselect_bin_id,
        image_mode=image_mode,
    ).run()


def run_search_form() -> Optional[str]:
    return _SearchFormApp().run()


def run_profile_form(user: dict) -> Optional[dict]:
    return _ProfileFormApp(user=user).run()
