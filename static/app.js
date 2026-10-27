// The browser half of the app. It shows the pages, lets you place things,
// and asks the Python server to build the final PDF.
//
// Positions are stored as fractions of the page (0 = left or top edge,
// 1 = right or bottom edge). That way they stay correct whatever size the
// page is drawn at on screen.

const $ = (id) => document.getElementById(id);

const state = {
  pdfId: null,
  pages: [],          // [{width, height}] in PDF points, one per page
  signatureId: null,  // the signature in use right now (photo or typed)
  signatureMode: "photo",  // "photo" or "typed"
  photoSignatureId: null,
  typedSignatureId: null,
  signatureRatio: 1,  // signature height divided by width, in pixels
  threshold: 200,
  tool: null,         // "signature", "text" or null
  items: [],          // everything placed on the pages
};

// A small wrapper around fetch that turns server errors into readable alerts.
async function callServer(url, options) {
  const response = await fetch(url, options);
  if (!response.ok) {
    let message = response.statusText;
    try { message = (await response.json()).error; } catch (e) {}
    throw new Error(message);
  }
  return response;
}

function setHint(text) { $("hint").textContent = text; }

// ---------- 1. Opening a PDF ----------

$("pdf-input").addEventListener("change", async (event) => {
  const file = event.target.files[0];
  if (!file) return;
  const form = new FormData();
  form.append("file", file);
  try {
    const result = await (await callServer("/api/pdf", { method: "POST", body: form })).json();
    state.pdfId = result.id;
    state.pages = result.pages;
    state.items = [];
    showPages();
    updateButtons();
    setHint("Now add a signature or some text, then click on the page to place it.");
  } catch (error) {
    alert(error.message);
  }
});

function showPages() {
  const container = $("pages");
  container.innerHTML = "";
  state.pages.forEach((size, index) => {
    const page = document.createElement("div");
    page.className = "page";
    page.dataset.index = index;
    page.style.aspectRatio = `${size.width} / ${size.height}`;
    const img = document.createElement("img");
    img.src = `/api/pdf/${state.pdfId}/page/${index}.png`;
    img.alt = `Page ${index + 1}`;
    img.addEventListener("click", (event) => placeItem(index, event));
    page.appendChild(img);
    container.appendChild(page);
  });
}

// ---------- 2. The signature ----------

$("signature-input").addEventListener("change", async (event) => {
  const file = event.target.files[0];
  if (!file) return;
  const form = new FormData();
  form.append("file", file);
  try {
    const result = await (await callServer("/api/signature", { method: "POST", body: form })).json();
    state.photoSignatureId = result.id;
    useSignature(result.id);
  } catch (error) {
    alert(error.message);
  }
});

// Switch to a new signature picture. Anything already placed on the pages
// switches too, so every signature in the PDF matches.
function useSignature(id) {
  state.signatureId = id;
  $("signature-preview").hidden = !id;
  $("threshold-row").hidden = !(id && state.signatureMode === "photo");
  if (id) refreshSignature();
  updateButtons();
}

// The "Upload a photo" and "Type it" switch.
function chooseSignatureMode(mode) {
  state.signatureMode = mode;
  $("mode-photo").classList.toggle("active", mode === "photo");
  $("mode-typed").classList.toggle("active", mode === "typed");
  $("photo-panel").hidden = mode !== "photo";
  $("typed-panel").hidden = mode !== "typed";
  useSignature(mode === "photo" ? state.photoSignatureId : state.typedSignatureId);
  if (mode === "typed") $("typed-name").focus();
}
$("mode-photo").addEventListener("click", () => chooseSignatureMode("photo"));
$("mode-typed").addEventListener("click", () => chooseSignatureMode("typed"));

// ---------- 2b. Typed signature ----------

// Ask the server to draw the typed name in the chosen font.
async function makeTypedSignature() {
  const text = $("typed-name").value.trim();
  if (!text) {
    state.typedSignatureId = null;
    useSignature(null);
    return;
  }
  const font = document.querySelector('input[name="font"]:checked').value;
  try {
    const result = await (await callServer("/api/signature/typed", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, font }),
    })).json();
    state.typedSignatureId = result.id;
    // Only use it if you are still on the "Type it" tab.
    if (state.signatureMode === "typed") useSignature(result.id);
  } catch (error) {
    alert(error.message);
  }
}

// As you type, show your name in every font so you can compare them.
// Wait until you pause typing for a moment before asking the server.
let typingTimer;
$("typed-name").addEventListener("input", () => {
  const text = $("typed-name").value.trim();
  document.querySelectorAll(".font-choice").forEach((choice) => {
    choice.querySelector(".font-sample").textContent = text || choice.title;
  });
  clearTimeout(typingTimer);
  typingTimer = setTimeout(makeTypedSignature, 300);
});
document.querySelectorAll('input[name="font"]').forEach((radio) => {
  radio.addEventListener("change", makeTypedSignature);
});

function signatureUrl() {
  return `/api/signature/${state.signatureId}.png?threshold=${state.threshold}`;
}

// Ask the server for a freshly cleaned signature, then update every copy.
function refreshSignature() {
  const preview = $("signature-img");
  preview.onload = () => {
    state.signatureRatio = preview.naturalHeight / preview.naturalWidth;
    state.items.filter((item) => item.type === "signature").forEach((item) => {
      item.el.querySelector("img").src = preview.src;
      keepSignatureShape(item);
      positionItem(item);
    });
  };
  preview.src = signatureUrl();
}

// Wait until the slider stops moving for a moment before asking the server.
let sliderTimer;
$("threshold").addEventListener("input", (event) => {
  state.threshold = Number(event.target.value);
  clearTimeout(sliderTimer);
  sliderTimer = setTimeout(refreshSignature, 150);
});

// ---------- 3. Text ----------

$("today").addEventListener("click", () => {
  $("text-value").value = new Date().toLocaleDateString();
  updateButtons();
});
$("text-value").addEventListener("input", updateButtons);

// ---------- Choosing what to place ----------

function chooseTool(tool) {
  state.tool = state.tool === tool ? null : tool;  // clicking again cancels
  $("place-signature").classList.toggle("active", state.tool === "signature");
  $("place-text").classList.toggle("active", state.tool === "text");
  document.body.classList.toggle("placing", state.tool !== null);
  if (state.tool) setHint("Click on a page where you want it to go.");
}
$("place-signature").addEventListener("click", () => chooseTool("signature"));
$("place-text").addEventListener("click", () => chooseTool("text"));

function updateButtons() {
  $("place-signature").disabled = !(state.pdfId && state.signatureId);
  $("place-text").disabled = !(state.pdfId && $("text-value").value.trim());
  $("download").disabled = !state.pdfId;
}

// ---------- Placing, moving and resizing ----------

function placeItem(pageIndex, event) {
  if (!state.tool) return;
  const pageBox = event.currentTarget.getBoundingClientRect();
  const clickX = (event.clientX - pageBox.left) / pageBox.width;
  const clickY = (event.clientY - pageBox.top) / pageBox.height;
  const size = state.pages[pageIndex];
  let item;

  if (state.tool === "signature") {
    // Start about 2 inches wide (144 points), centred on the click.
    const width = Math.min(144 / size.width, 0.9);
    item = { type: "signature", page: pageIndex, width };
    keepSignatureShape(item);
    item.x = clickX - item.width / 2;
    item.y = clickY - item.height / 2;
  } else {
    // The click marks the left edge of the text, halfway up the letters.
    const fontSize = Number($("text-size").value) || 12;
    item = {
      type: "text",
      page: pageIndex,
      text: $("text-value").value,
      size: fontSize,
      x: clickX,
      y: clickY - fontSize / 2 / size.height,
    };
  }

  item.el = makeItemElement(item);
  document.querySelector(`.page[data-index="${pageIndex}"]`).appendChild(item.el);
  state.items.push(item);
  positionItem(item);
  chooseTool(null);
  setHint("Drag to move. Drag the blue dot to resize. Double-click text to edit it.");
}

// Signatures keep their shape when resized. Because pages are not square,
// we convert through PDF points to get the height right.
function keepSignatureShape(item) {
  const size = state.pages[item.page];
  item.height = (item.width * size.width * state.signatureRatio) / size.height;
}

function makeItemElement(item) {
  const el = document.createElement("div");
  el.className = `item ${item.type}`;
  if (item.type === "signature") {
    const img = document.createElement("img");
    img.src = signatureUrl();
    el.appendChild(img);
  } else {
    el.appendChild(document.createTextNode(item.text));
    el.addEventListener("dblclick", () => {
      const newText = prompt("Edit text", item.text);
      if (newText) {
        item.text = newText;
        el.firstChild.textContent = newText;
      }
    });
  }

  const remove = document.createElement("div");
  remove.className = "delete";
  remove.textContent = "×";
  remove.title = "Remove";
  remove.addEventListener("click", () => {
    el.remove();
    state.items = state.items.filter((other) => other !== item);
  });

  const resize = document.createElement("div");
  resize.className = "resize";
  resize.title = "Drag to resize";

  el.append(remove, resize);
  el.addEventListener("pointerdown", (event) => startDrag(item, event));
  return el;
}

// Put the element on screen to match the item's fractions.
function positionItem(item) {
  const el = item.el;
  el.style.left = `${item.x * 100}%`;
  el.style.top = `${item.y * 100}%`;
  if (item.type === "signature") {
    el.style.width = `${item.width * 100}%`;
    el.style.height = `${item.height * 100}%`;
  } else {
    // Turn the font size in points into screen pixels for this page.
    const pageWidthOnScreen = el.parentElement.getBoundingClientRect().width;
    el.style.fontSize = `${(item.size * pageWidthOnScreen) / state.pages[item.page].width}px`;
  }
}

function startDrag(item, event) {
  if (event.target.classList.contains("delete")) return;
  event.preventDefault();
  const resizing = event.target.classList.contains("resize");
  const pageBox = item.el.parentElement.getBoundingClientRect();
  const start = { mouseX: event.clientX, mouseY: event.clientY, x: item.x, y: item.y,
                  width: item.width, size: item.size, pixels: item.el.getBoundingClientRect().width };
  item.el.classList.add("dragging");

  function onMove(moveEvent) {
    const dx = moveEvent.clientX - start.mouseX;
    const dy = moveEvent.clientY - start.mouseY;
    if (resizing) {
      const scale = Math.max(0.1, (start.pixels + dx) / start.pixels);
      if (item.type === "signature") {
        item.width = start.width * scale;
        keepSignatureShape(item);
      } else {
        item.size = Math.max(4, Math.round(start.size * scale * 2) / 2);
      }
    } else {
      item.x = start.x + dx / pageBox.width;
      item.y = start.y + dy / pageBox.height;
    }
    positionItem(item);
  }

  function onUp() {
    item.el.classList.remove("dragging");
    window.removeEventListener("pointermove", onMove);
    window.removeEventListener("pointerup", onUp);
  }

  window.addEventListener("pointermove", onMove);
  window.addEventListener("pointerup", onUp);
}

// Keep text the right size when the window changes size.
window.addEventListener("resize", () => state.items.forEach(positionItem));

// ---------- 4. Download ----------

$("download").addEventListener("click", async () => {
  // Only send the plain data, not the on-screen elements.
  const items = state.items.map(({ el, ...data }) => data);
  try {
    const response = await callServer(`/api/pdf/${state.pdfId}/sign`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ items, signatureId: state.signatureId, threshold: state.threshold }),
    });
    // Pull the file name out of the server's reply, then save the file.
    const header = response.headers.get("Content-Disposition") || "";
    const match = header.match(/filename="?([^"]+)"?/);
    const link = document.createElement("a");
    link.href = URL.createObjectURL(await response.blob());
    link.download = match ? match[1] : "signed.pdf";
    link.click();
    setTimeout(() => URL.revokeObjectURL(link.href), 1000);
    setHint("Saved. Check your Downloads folder.");
  } catch (error) {
    alert(error.message);
  }
});
