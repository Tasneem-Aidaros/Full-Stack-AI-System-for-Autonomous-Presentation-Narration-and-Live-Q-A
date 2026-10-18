import { useState } from "react";
import { slideImageUrl } from "../api.js";

const SPEEDS = [0.5, 0.75, 1, 1.25, 1.5, 2];

const LIVE_STATUSES = ["starting", "generating_script", "opening_powerpoint", "presenting"];

const MODE_LABELS = {
  narration: null,
  acknowledging: "🎤 Presenter",
  question: "🎤 You asked",
  answering: "💬 Answer",
};

export default function Player({
  status,
  paused,
  currentSlide,
  totalSlides,
  subtitle,
  subtitleMode,
  speed,
  onStart,
  onContinue,
  onStop,
  onPlayPause,
  onSeekBack,
  onSeekForward,
  onSpeedChange,
  onPrevSlide,
  onNextSlide,
}) {
  const [imageFailed, setImageFailed] = useState(false);

  const isLive = LIVE_STATUSES.includes(status);
  const canContinue = status === "stopped" && currentSlide > 0;
  const hasSlideImage = currentSlide > 0 && !imageFailed;

  return (
    <div className="panel player">
      <div className="player__screen">
        {hasSlideImage ? (
          <img
            className="player__slide-image"
            src={slideImageUrl(currentSlide)}
            alt={`Slide ${currentSlide}`}
            onError={() => setImageFailed(true)}
            onLoad={() => setImageFailed(false)}
          />
        ) : (
          <div className="player__placeholder">
            {status === "idle" ? "Load a deck and hit start." : "Slide image not available."}
          </div>
        )}

        {subtitle && (
          <div className={`player__caption-overlay${subtitleMode !== "narration" ? " player__caption-overlay--qa" : ""}`}>
            {MODE_LABELS[subtitleMode] && (
              <div className="player__caption-badge">{MODE_LABELS[subtitleMode]}</div>
            )}
            {subtitle}
          </div>
        )}
      </div>

      <div className="player__controls">
        <button
          className="player__btn"
          onClick={onSeekBack}
          disabled={!isLive}
          title="Back ~10s"
        >
          ⏪
        </button>

        {isLive ? (
          <button className="player__btn player__btn--primary" onClick={onPlayPause}>
            {paused ? "▶" : "⏸"}
          </button>
        ) : canContinue ? (
          <button className="player__btn player__btn--primary" onClick={onContinue}>
            ▶ Continue
          </button>
        ) : (
          <button className="player__btn player__btn--primary" onClick={onStart}>
            ▶ Start
          </button>
        )}

        <button
          className="player__btn"
          onClick={onSeekForward}
          disabled={!isLive}
          title="Forward ~10s"
        >
          ⏩
        </button>

        <button className="player__btn player__btn--stop" onClick={onStop} disabled={!isLive}>
          ■
        </button>

        <button
          className="player__btn"
          onClick={onPrevSlide}
          disabled={!isLive || currentSlide <= 1}
          title="Previous slide"
        >
          ⏮
        </button>

        <span className="player__slide-counter">
          {currentSlide || 0} / {totalSlides}
        </span>

        <button
          className="player__btn"
          onClick={onNextSlide}
          disabled={!isLive || currentSlide >= totalSlides}
          title="Next slide"
        >
          ⏭
        </button>

        <div className="player__tempo">
          {SPEEDS.map((s) => (
            <button
              key={s}
              className={`tempo-btn${speed === s ? " tempo-btn--active" : ""}`}
              onClick={() => onSpeedChange(s)}
            >
              {s}x
            </button>
          ))}
        </div>
      </div>

      {canContinue && (
        <button className="player__start-over" onClick={onStart}>
          or start over from slide 1
        </button>
      )}
    </div>
  );
}
