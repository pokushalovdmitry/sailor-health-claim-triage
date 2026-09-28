const chatLog = document.getElementById("chat-log");
const dropzone = document.getElementById("dropzone");
const fileInput = document.getElementById("file-input");
const uploadBtn = document.getElementById("upload-btn");

const DECISION_LABEL = {
  pursue: "Pursue",
  pursue_expedite: "Pursue, but expedite filing",
  do_not_pursue: "Do not pursue",
};

function addBubble(role, html) {
  const div = document.createElement("div");
  div.className = `bubble ${role}`;
  div.innerHTML = html;
  chatLog.appendChild(div);
  window.scrollTo(0, document.body.scrollHeight);
  return div;
}

function escapeHtml(s) {
  const d = document.createElement("div");
  d.textContent = s;
  return d.innerHTML;
}

addBubble(
  "assistant",
  "Please upload the denial notice to estimate whether it's worth pursuing an appeal."
);

// Extra breathing room after the claim-identification paragraph (0), the
// expected-revenue paragraph (2), and the final net-profit paragraph (4) --
// groups the 5 paragraphs into 3 visual blocks: identification, economics
// estimate, bottom line.
const EXTRA_SPACE_AFTER = new Set([0, 2, 4]);

function renderParagraph(segments, index) {
  const html = segments
    .map((seg) => {
      let text = escapeHtml(seg.text);
      if (seg.bold) text = `<strong>${text}</strong>`;
      if (seg.italic) text = `<em>${text}</em>`;
      return text;
    })
    .join("");
  const extraClass = EXTRA_SPACE_AFTER.has(index) ? " space-after" : "";
  return `<p class="${extraClass.trim()}">${html}</p>`;
}

function renderResult(data, filename) {
  if (!data.valid) {
    addBubble(
      "error",
      escapeHtml(data.message || "Unrecognized format -- please upload a claim denial notice in a recognized format.") +
        (data.detail ? `<br><span style="font-size:12px;opacity:0.8;">${escapeHtml(data.detail)}</span>` : "")
    );
    return;
  }

  const decisionClass = data.decision;
  const decisionLabel = DECISION_LABEL[data.decision] || data.decision;

  const paragraphsHtml = data.paragraphs.map((p, i) => renderParagraph(p, i)).join("");

  addBubble(
    "assistant",
    `
    <div class="decision-pill ${decisionClass}">${escapeHtml(decisionLabel)}</div>
    <p class="headline ${decisionClass}">${escapeHtml(data.headline)}</p>
    <p class="rationale">${escapeHtml(data.rationale)}</p>
    <div class="result-body">${paragraphsHtml}</div>
    `
  );
}

async function handleFile(file) {
  if (!file) return;
  addBubble("user", `Uploaded: ${escapeHtml(file.name)}`);

  const loadingBubble = addBubble("assistant", `<span class="spinner"></span> Analyzing denial notice...`);

  const formData = new FormData();
  formData.append("file", file);

  try {
    const resp = await fetch("/api/analyze", { method: "POST", body: formData });
    const data = await resp.json();
    loadingBubble.remove();
    renderResult(data, file.name);
  } catch (err) {
    loadingBubble.remove();
    addBubble("error", "Something went wrong while analyzing this file. Please try again.");
    console.error(err);
  }

  fileInput.value = "";
}

dropzone.addEventListener("click", () => fileInput.click());
uploadBtn.addEventListener("click", () => fileInput.click());

fileInput.addEventListener("change", (e) => {
  handleFile(e.target.files[0]);
});

["dragenter", "dragover"].forEach((evt) =>
  dropzone.addEventListener(evt, (e) => {
    e.preventDefault();
    dropzone.classList.add("drag-over");
  })
);

["dragleave", "drop"].forEach((evt) =>
  dropzone.addEventListener(evt, (e) => {
    e.preventDefault();
    dropzone.classList.remove("drag-over");
  })
);

dropzone.addEventListener("drop", (e) => {
  const file = e.dataTransfer.files[0];
  handleFile(file);
});
