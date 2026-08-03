"""Textual-based forms for BinInventory CLI.

Public API
----------
run_bin_form(existing=None)                              -> Optional[dict]
run_item_form(bins, existing=None, preselect_bin_id=None) -> Optional[dict]

Returns a dict of field values on save, or None on cancel.
All fields are shown at once; Tab / Shift+Tab to move between them,
Ctrl+S to save, Escape to cancel.
"""

from datetime import datetime
from typing import List, Optional

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, ScrollableContainer
from textual.widgets import Button, Footer, Input, Label, Select, Static, Switch


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


# ── Shared CSS — retro VT100 phosphor aesthetic ────────────────────────────────

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
.lbl {
    width: 16;
    height: 1;
    content-align: right middle;
    color: #55ffff;
    background: #000080;
}
.lbl-req {
    color: #ffff55;
    text-style: bold;
}
Input {
    width: 1fr;
    height: 1;
    border: none;
    background: #000050;
    color: #ffffff;
    padding: 0 1;
}
Input:focus {
    background: #000068;
    border: none;
    color: #ffff55;
}
Select {
    width: 1fr;
    background: #000050;
    color: #ffffff;
    border: none;
}
Select:focus {
    background: #000068;
    color: #ffff55;
}
Switch {
    background: #000080;
    height: 1;
    border: none;
}
#img-note {
    color: #5555aa;
    height: 1;
    width: 1fr;
    content-align: left middle;
    background: #000080;
    padding-left: 1;
}
#buttons {
    height: 3;
    align: center middle;
    background: #000080;
    border-top: solid #005588;
    margin-top: 1;
}
Button {
    background: #000080;
    color: #55ffff;
    border: solid #005588;
    margin: 0 2;
    min-width: 14;
}
Button:focus {
    background: #000060;
    color: #ffff55;
    border: solid #55ffff;
}
Button.-primary {
    color: #ffff55;
    border: solid #55ffff;
}
"""


# ── Bin form ───────────────────────────────────────────────────────────────────

class _BinFormApp(App):
    BINDINGS = [
        Binding("ctrl+s", "save", "Save"),
        Binding("escape", "cancel", "Cancel"),
    ]
    DEFAULT_CSS = _CSS

    def __init__(self, existing: Optional[dict] = None):
        super().__init__()
        self._existing = existing or {}

    def compose(self) -> ComposeResult:
        b = self._existing
        title = f"BinInventory  --  {'Edit Bin: ' + b['binName'] if b else 'New Bin'}"
        yield Static(title, id="form-title")
        yield Static(
            "Tab/Shift+Tab: move   Ctrl+S: save   Esc: cancel",
            id="form-hint",
        )
        with ScrollableContainer(id="fields"):
            with Horizontal(classes="row"):
                yield Label("Name :", classes="lbl lbl-req")
                yield Input(value=b.get("binName", ""), id="bin_name", placeholder="required")
            with Horizontal(classes="row"):
                yield Label("Description :", classes="lbl")
                yield Input(value=b.get("description", "") or "", id="description")
            with Horizontal(classes="row"):
                yield Label("Location :", classes="lbl")
                yield Input(value=b.get("location", "") or "", id="location")
            with Horizontal(classes="row"):
                yield Label("Type :", classes="lbl")
                yield Input(value=b.get("type", "") or "", id="bin_type")
            with Horizontal(classes="row"):
                yield Label("Public :", classes="lbl")
                yield Switch(value=bool(b.get("public", False)), id="public")
            with Horizontal(classes="row"):
                yield Label("Share with :", classes="lbl")
                yield Input(
                    value=" ".join(b.get("sharedWith", [])),
                    id="sw_emails",
                    placeholder="space-separated emails",
                )
            with Horizontal(classes="row"):
                yield Label("Image :", classes="lbl")
                current_img = b.get("image", "")
                ph = "leave blank to keep existing" if current_img else "file path or leave blank"
                yield Input(value="", id="image_path", placeholder=ph)
        with Horizontal(id="buttons"):
            yield Button("[ SAVE ]", variant="primary", id="save")
            yield Button("[ CANCEL ]", id="cancel")

    def on_mount(self) -> None:
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
            "public": self.query_one("#public", Switch).value,
            "sw_emails": self.query_one("#sw_emails", Input).value.strip(),
            "image_path": self.query_one("#image_path", Input).value.strip() or None,
        })

    def action_cancel(self) -> None:
        self.exit(None)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "save":
            self.action_save()
        elif event.button.id == "cancel":
            self.action_cancel()


# ── Item form ──────────────────────────────────────────────────────────────────

class _ItemFormApp(App):
    BINDINGS = [
        Binding("ctrl+s", "save", "Save"),
        Binding("escape", "cancel", "Cancel"),
    ]
    DEFAULT_CSS = _CSS

    def __init__(
        self,
        bins: list,
        existing: Optional[dict] = None,
        preselect_bin_id: Optional[str] = None,
    ):
        super().__init__()
        self._bins = bins
        self._existing = existing or {}
        self._preselect_bin_id = preselect_bin_id

    def compose(self) -> ComposeResult:
        it = self._existing
        title = f"BinInventory  --  {'Edit Item: ' + it['item'] if it else 'New Item'}"
        yield Static(title, id="form-title")
        yield Static(
            "Tab/Shift+Tab: move   Ctrl+S: save   Esc: cancel",
            id="form-hint",
        )

        current_bin_id = _bin_id_from_item(it) or self._preselect_bin_id
        bin_options = [(b["binName"], b["id"]) for b in self._bins]
        selected_bin = current_bin_id if current_bin_id else (bin_options[0][1] if bin_options else None)
        existing_imgs = _item_images(it)

        with ScrollableContainer(id="fields"):
            with Horizontal(classes="row"):
                yield Label("Name :", classes="lbl lbl-req")
                yield Input(value=it.get("item", ""), id="item_name", placeholder="required")
            with Horizontal(classes="row"):
                yield Label("Bin :", classes="lbl lbl-req")
                yield Select(options=bin_options, value=selected_bin, id="bin_id", allow_blank=False)
            with Horizontal(classes="row"):
                yield Label("Description :", classes="lbl")
                yield Input(value=it.get("description", "") or "", id="description")
            with Horizontal(classes="row"):
                yield Label("Story :", classes="lbl")
                yield Input(value=it.get("story", "") or "", id="story")
            with Horizontal(classes="row"):
                yield Label("Type :", classes="lbl")
                yield Input(value=it.get("type", "") or "", id="item_type")
            with Horizontal(classes="row"):
                yield Label("Quantity :", classes="lbl")
                qty = str(it.get("quantity", "")) if it.get("quantity") is not None else ""
                yield Input(value=qty, id="quantity")
            with Horizontal(classes="row"):
                yield Label("Purch. date :", classes="lbl")
                yield Input(
                    value=_fmt_date(it.get("purchaseDate")),
                    id="purchase_date",
                    placeholder="YYYY-MM-DD",
                )
            with Horizontal(classes="row"):
                yield Label("Purch. from :", classes="lbl")
                yield Input(value=it.get("purchasedFrom", "") or "", id="purchased_from")
            with Horizontal(classes="row"):
                yield Label("Mfr. :", classes="lbl")
                yield Input(value=it.get("manufacturer", "") or "", id="manufacturer")
            with Horizontal(classes="row"):
                yield Label("Mfr. date :", classes="lbl")
                yield Input(
                    value=_fmt_date(it.get("dateOfManufacture")),
                    id="date_of_manufacture",
                    placeholder="YYYY-MM-DD",
                )
            with Horizontal(classes="row"):
                yield Label("Serial # :", classes="lbl")
                yield Input(value=it.get("serialNumber", "") or "", id="serial_number")
            with Horizontal(classes="row"):
                yield Label("Price :", classes="lbl")
                price = str(it.get("purchasePrice", "")) if it.get("purchasePrice") is not None else ""
                yield Input(value=price, id="purchase_price")
            if existing_imgs:
                with Horizontal(classes="row"):
                    yield Label("Keep imgs :", classes="lbl")
                    yield Switch(value=True, id="keep_images")
                with Horizontal(classes="row"):
                    yield Label("", classes="lbl")
                    yield Static(
                        f"{len(existing_imgs)} existing  (toggle off to remove all)",
                        id="img-note",
                    )
            with Horizontal(classes="row"):
                yield Label("New imgs :", classes="lbl")
                yield Input(value="", id="new_images", placeholder="comma-separated file paths")
        with Horizontal(id="buttons"):
            yield Button("[ SAVE ]", variant="primary", id="save")
            yield Button("[ CANCEL ]", id="cancel")

    def on_mount(self) -> None:
        self.query_one("#item_name", Input).focus()

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

        it = self._existing
        existing_imgs = _item_images(it)

        try:
            keep = self.query_one("#keep_images", Switch).value
        except Exception:
            keep = True
        kept = existing_imgs if keep else []

        new_raw = ""
        try:
            new_raw = self.query_one("#new_images", Input).value.strip()
        except Exception:
            pass
        new_paths = [p.strip() for p in new_raw.split(",") if p.strip()]

        self.exit({
            "item": item_name,
            "bin_id": bin_id,
            "description": self.query_one("#description", Input).value.strip(),
            "story": self.query_one("#story", Input).value.strip(),
            "item_type": self.query_one("#item_type", Input).value.strip(),
            "quantity": self.query_one("#quantity", Input).value.strip(),
            "purchase_date": self.query_one("#purchase_date", Input).value.strip(),
            "purchased_from": self.query_one("#purchased_from", Input).value.strip(),
            "manufacturer": self.query_one("#manufacturer", Input).value.strip(),
            "date_of_manufacture": self.query_one("#date_of_manufacture", Input).value.strip(),
            "serial_number": self.query_one("#serial_number", Input).value.strip(),
            "purchase_price": self.query_one("#purchase_price", Input).value.strip(),
            "existing_images": kept,
            "new_image_paths": new_paths or None,
        })

    def action_cancel(self) -> None:
        self.exit(None)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "save":
            self.action_save()
        elif event.button.id == "cancel":
            self.action_cancel()


# ── Public API ─────────────────────────────────────────────────────────────────

def run_bin_form(existing: Optional[dict] = None) -> Optional[dict]:
    """Show the bin form. Returns field dict on save, None on cancel."""
    return _BinFormApp(existing=existing).run()


def run_item_form(
    bins: list,
    existing: Optional[dict] = None,
    preselect_bin_id: Optional[str] = None,
) -> Optional[dict]:
    """Show the item form. Returns field dict on save, None on cancel."""
    return _ItemFormApp(
        bins=bins,
        existing=existing,
        preselect_bin_id=preselect_bin_id,
    ).run()
