import { useState, useRef, useEffect } from "react";

export default function UploadPanel({ onUpload, uploading }) {
  const [dragActive, setDragActive] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const inputRef = useRef(null);

  // Show a running timer while uploading, so a slow upload looks alive
  // and a stuck one is obvious.
  useEffect(() => {
    if (!uploading) {
      setElapsed(0);
      return;
    }

    const startedAt = Date.now();

    const interval = setInterval(() => {
      setElapsed(Math.floor((Date.now() - startedAt) / 1000));
    }, 1000);

    return () => clearInterval(interval);
  }, [uploading]);

  const handleFile = (file) => {
    if (file) onUpload(file);
  };

  return (
    <div className="panel">
      <p className="panel__label">Load Deck</p>

      <div
        className={`dropzone${dragActive ? " dropzone--active" : ""}`}
        onDragOver={(e) => {
          e.preventDefault();
          setDragActive(true);
        }}
        onDragLeave={() => setDragActive(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragActive(false);
          handleFile(e.dataTransfer.files[0]);
        }}
      >
        {uploading ? (
          <>
            <div>Reading slides, exporting images, preparing script… {elapsed}s</div>
            <div className="dropzone__hint">
              {elapsed < 60
                ? "A new deck can take a minute or two. Re-uploading a deck you used before is instant."
                : "Taking longer than usual. Check the Backend window: its last line shows what it is doing."}
            </div>
          </>
        ) : (
          <>
            Drop a .pptx file here, or{" "}
            <label htmlFor="file-input">choose one</label>
            <input
              id="file-input"
              ref={inputRef}
              type="file"
              accept=".pptx"
              onChange={(e) => handleFile(e.target.files[0])}
            />
          </>
        )}
      </div>
    </div>
  );
}
