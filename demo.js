const tabButtons = Array.from(document.querySelectorAll(".demo-tab"));
const panels = Array.from(document.querySelectorAll(".demo-panel"));

const generateKeysButton = document.getElementById("generate-keys-button");
const generateResult = document.getElementById("generate-result");
const keyPill = document.getElementById("key-pill");

const signForm = document.getElementById("sign-form");
const signFileInput = document.getElementById("sign-file");
const signButton = document.getElementById("sign-button");
const signResult = document.getElementById("sign-result");
const signPreview = document.getElementById("sign-preview");
const signPreviewVideo = document.getElementById("sign-preview-video");
const signPreviewEmpty = document.getElementById("sign-preview-empty");
const downloadLink = document.getElementById("download-link");

const verifyForm = document.getElementById("verify-form");
const verifyFileInput = document.getElementById("verify-file");
const verifyButton = document.getElementById("verify-button");
const verifyPreview = document.getElementById("verify-preview");
const verifyPreviewVideo = document.getElementById("verify-preview-video");
const verifyPreviewEmpty = document.getElementById("verify-preview-empty");
const verifyResultCard = document.getElementById("verify-result-card");
const verifyStatus = document.getElementById("verify-status");
const verifyDetail = document.getElementById("verify-detail");

const LOCAL_FILE_ERROR =
  "Open the demo through the local server. Run run_demo.bat or start app.py, then use http://127.0.0.1:5000/demo.";

function activateTab(panelName) {
  tabButtons.forEach((button) => {
    const isActive = button.dataset.panel === panelName;
    button.classList.toggle("active", isActive);
    button.setAttribute("aria-pressed", String(isActive));
  });

  panels.forEach((panel) => {
    panel.classList.toggle("active", panel.id === `panel-${panelName}`);
  });
}

function setBanner(element, tone, message) {
  element.className = `result-banner ${tone}`;
  element.textContent = message;
}

function setVerifyCard(tone, status, detail) {
  verifyResultCard.classList.remove("authentic-state", "danger-state", "info-state");
  verifyResultCard.classList.add(`${tone}-state`);
  verifyStatus.textContent = status;
  verifyDetail.textContent = detail;
}

function setKeyStatus(hasKeys, message) {
  keyPill.textContent = hasKeys ? "RSA keys ready" : "RSA keys missing";
  keyPill.classList.toggle("success", hasKeys);
  keyPill.classList.toggle("danger", !hasKeys);
  signButton.disabled = !hasKeys;
  if (message) {
    setBanner(generateResult, hasKeys ? "success" : "info", message);
  }
}

function setLoading(button, loadingText, isLoading) {
  if (!button.dataset.originalText) {
    button.dataset.originalText = button.textContent;
  }
  button.disabled = isLoading;
  button.textContent = isLoading ? loadingText : button.dataset.originalText;
}

function resetPreview(imageElement, videoElement, emptyElement) {
  imageElement.classList.add("hidden");
  imageElement.removeAttribute("src");
  videoElement.classList.add("hidden");
  videoElement.pause();
  videoElement.removeAttribute("src");
  videoElement.load();
  emptyElement.classList.remove("hidden");
}

function previewSelectedFile(file, imageElement, videoElement, emptyElement) {
  if (!file) {
    resetPreview(imageElement, videoElement, emptyElement);
    return;
  }

  const objectUrl = URL.createObjectURL(file);
  const isVideo = file.type.startsWith("video/") || /\.(mp4|mov|avi|mkv|m4v)$/i.test(file.name);

  if (isVideo) {
    imageElement.classList.add("hidden");
    imageElement.removeAttribute("src");
    videoElement.src = objectUrl;
    videoElement.classList.remove("hidden");
  } else {
    videoElement.classList.add("hidden");
    videoElement.pause();
    videoElement.removeAttribute("src");
    videoElement.load();
    imageElement.src = objectUrl;
    imageElement.classList.remove("hidden");
  }
  emptyElement.classList.add("hidden");
}

async function fetchJson(url, options = {}) {
  if (window.location.protocol === "file:") {
    throw new Error(LOCAL_FILE_ERROR);
  }

  const response = await fetch(url, options);
  const payload = await response.json().catch(() => ({
    ok: false,
    message: "Server returned an unreadable response.",
  }));

  if (!response.ok || payload.ok === false) {
    throw new Error(payload.message || "Request failed.");
  }

  return payload;
}

async function refreshStatus() {
  try {
    const status = await fetchJson("/api/status");
    setKeyStatus(status.hasKeys, status.hasKeys ? "RSA key pair is already available for signing." : "Generate the RSA key pair before signing.");
  } catch (error) {
    setKeyStatus(false, `Unable to reach demo backend: ${error.message}`);
  }
}

tabButtons.forEach((button) => {
  button.addEventListener("click", () => activateTab(button.dataset.panel));
});

generateKeysButton.addEventListener("click", async () => {
  setLoading(generateKeysButton, "Generating...", true);
  try {
    const payload = await fetchJson("/api/generate-keys", {
      method: "POST",
    });
    setKeyStatus(true, payload.message);
    setBanner(generateResult, "success", payload.message);
  } catch (error) {
    setBanner(generateResult, "danger", error.message);
    setKeyStatus(false);
  } finally {
    setLoading(generateKeysButton, "Generating...", false);
  }
});

signFileInput.addEventListener("change", () => {
  previewSelectedFile(signFileInput.files[0], signPreview, signPreviewVideo, signPreviewEmpty);
  downloadLink.classList.add("hidden");
});

verifyFileInput.addEventListener("change", () => {
  previewSelectedFile(verifyFileInput.files[0], verifyPreview, verifyPreviewVideo, verifyPreviewEmpty);
});

signForm.addEventListener("submit", async (event) => {
  event.preventDefault();

  const file = signFileInput.files[0];
  if (!file) {
    setBanner(signResult, "danger", "Choose a screenshot or video before signing.");
    return;
  }

  const formData = new FormData();
  formData.append("file", file);
  const isVideo = file.type.startsWith("video/") || /\.(mp4|mov|avi|mkv|m4v)$/i.test(file.name);

  setLoading(signButton, "Signing...", true);
  setBanner(
    signResult,
    "info",
    isVideo
      ? "Signing video moments and embedding hidden proof..."
      : "Signing image and embedding hidden proof...",
  );
  downloadLink.classList.add("hidden");

  try {
    const payload = await fetchJson("/api/sign", {
      method: "POST",
      body: formData,
    });
    const detail = payload.detail ? ` ${payload.detail}` : "";
    setBanner(signResult, "success", `${payload.message}${detail} Signature: ${payload.signaturePreview}`);
    downloadLink.href = payload.downloadUrl;
    downloadLink.classList.remove("hidden");
    downloadLink.click();
  } catch (error) {
    setBanner(signResult, "danger", error.message);
  } finally {
    setLoading(signButton, "Signing...", false);
  }
});

verifyForm.addEventListener("submit", async (event) => {
  event.preventDefault();

  const file = verifyFileInput.files[0];
  if (!file) {
    setVerifyCard("danger", "Verification unavailable", "Choose media before running verification.");
    return;
  }

  const formData = new FormData();
  formData.append("file", file);
  const isVideo = file.type.startsWith("video/") || /\.(mp4|mov|avi|mkv|m4v)$/i.test(file.name);

  setLoading(verifyButton, "Verifying...", true);
  setVerifyCard(
    "info",
    "Verifying...",
    isVideo
      ? "Checking signed moments across the video timeline."
      : "Checking watermark extraction, signature validity, and fingerprint match.",
  );

  try {
    const payload = await fetchJson("/api/verify", {
      method: "POST",
      body: formData,
    });

    if (payload.isAuthentic) {
      setVerifyCard("authentic", payload.status, payload.detail);
      return;
    }

    setVerifyCard("danger", payload.status, payload.detail);
  } catch (error) {
    setVerifyCard("danger", "Verification failed", error.message);
  } finally {
    setLoading(verifyButton, "Verifying...", false);
  }
});

const revealObserver = new IntersectionObserver(
  (entries) => {
    entries.forEach((entry) => {
      if (entry.isIntersecting) {
        entry.target.classList.add("is-visible");
        revealObserver.unobserve(entry.target);
      }
    });
  },
  {
    threshold: 0.12,
  },
);

document.querySelectorAll(".reveal").forEach((element) => {
  revealObserver.observe(element);
});

setVerifyCard("info", "Waiting for verification", "Upload media and run verification to see whether the proof is valid.");
refreshStatus();
