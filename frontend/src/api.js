// Change this if your backend runs somewhere other than the default
// uvicorn address.
export const API_BASE = "http://127.0.0.1:8000";

// Uploading a new deck can legitimately take a minute or two (PowerPoint
// export + Gemini). Past this, something is stuck, so show an error
// instead of spinning forever.
const UPLOAD_TIMEOUT_MS = 5 * 60 * 1000;

async function request(path, options = {}) {
  let response;

  try {
    response = await fetch(`${API_BASE}${path}`, options);
  } catch (err) {
    if (err.name === "AbortError") throw err;

    throw new Error(
      `Cannot reach the backend at ${API_BASE}. Is the backend window still running?`
    );
  }

  if (!response.ok) {
    let detail = response.statusText;

    try {
      const body = await response.json();
      detail = body.detail || detail;
    } catch {
      // response wasn't JSON, fall back to statusText
    }

    throw new Error(detail);
  }

  return response.json();
}

export async function uploadPresentation(file, forceRegenerate = false) {
  const formData = new FormData();
  formData.append("file", file);

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), UPLOAD_TIMEOUT_MS);

  try {
    return await request(`/upload?force_regenerate=${forceRegenerate}`, {
      method: "POST",
      body: formData,
      signal: controller.signal,
    });
  } catch (err) {
    if (err.name === "AbortError") {
      throw new Error(
        "The upload took more than 5 minutes. Look at the Backend window for the last message, it shows where it got stuck."
      );
    }

    throw err;
  } finally {
    clearTimeout(timer);
  }
}

export function getPresentation() {
  return request("/presentation");
}

export function startPresentation(resume = false) {
  return request(`/start_presentation?resume=${resume}`, { method: "POST" });
}

export function stopPresentation() {
  return request("/stop_presentation", { method: "POST" });
}

export function pausePresentation() {
  return request("/pause", { method: "POST" });
}

export function resumePresentation() {
  return request("/resume", { method: "POST" });
}

export function seekBack() {
  return request("/seek/back", { method: "POST" });
}

export function seekForward() {
  return request("/seek/forward", { method: "POST" });
}

export function nextSlide() {
  return request("/slide/next", { method: "POST" });
}

export function previousSlide() {
  return request("/slide/previous", { method: "POST" });
}

export function gotoSlide(slideNumber) {
  return request(`/slide/${slideNumber}/goto`, { method: "POST" });
}

export function slideImageUrl(slideNumber) {
  return `${API_BASE}/slide-images/Slide${slideNumber}.PNG`;
}

export function getPresentationStatus() {
  return request("/presentation-status");
}

export function getSubtitle() {
  return request("/subtitle");
}

export function getSpeechSpeed() {
  return request("/speech-speed");
}

export function setSpeechSpeed(speed) {
  return request("/speech-speed", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ speed }),
  });
}

export function askQuestion(question) {
  return request("/ask", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question }),
  });
}

export function getChatHistory() {
  return request("/chat-history");
}
