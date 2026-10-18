export default function StatusBar({ status, currentSlide, totalSlides }) {
  const isLive = status === "presenting" || status === "opening_powerpoint" || status === "generating_script" || status === "starting";
  const isError = status === "error";

  let tallyClass = "tally";
  let tallyText = "Standby";

  if (isError) {
    tallyClass = "tally tally--error";
    tallyText = "Error";
  } else if (isLive) {
    tallyClass = "tally tally--live";
    tallyText = "On Air";
  } else if (status === "finished") {
    tallyText = "Finished";
  } else if (status === "stopped") {
    tallyText = "Stopped";
  }

  return (
    <div className="status-bar">
      <div className="status-bar__title">
        <span className="status-bar__dot" />
        AI Presenter — Console
      </div>

      <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
        {totalSlides > 0 && (
          <span className="status-bar__slide">
            Slide {currentSlide || 0} / {totalSlides}
          </span>
        )}

        <span className={tallyClass}>
          <span className="tally__light" />
          {tallyText}
        </span>
      </div>
    </div>
  );
}
