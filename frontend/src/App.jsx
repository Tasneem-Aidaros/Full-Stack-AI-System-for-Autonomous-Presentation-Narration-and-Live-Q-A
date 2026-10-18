import { useState, useEffect, useCallback } from "react";
import StatusBar from "./components/StatusBar.jsx";
import UploadPanel from "./components/UploadPanel.jsx";
import Player from "./components/Player.jsx";
import IntercomPanel from "./components/IntercomPanel.jsx";
import * as api from "./api.js";

const SUBTITLE_POLL_MS = 400;
const STATUS_POLL_MS = 1000;
const HISTORY_POLL_MS = 1800;

export default function App() {
  const [deckLoaded, setDeckLoaded] = useState(false);
  const [totalSlides, setTotalSlides] = useState(0);

  const [status, setStatus] = useState("idle");
  const [paused, setPaused] = useState(false);
  const [audioError, setAudioError] = useState("");
  const [currentSlide, setCurrentSlide] = useState(0);
  const [subtitle, setSubtitle] = useState("");
  const [subtitleMode, setSubtitleMode] = useState("narration");
  const [speed, setSpeed] = useState(1);
  const [history, setHistory] = useState([]);

  const [uploading, setUploading] = useState(false);
  const [asking, setAsking] = useState(false);
  const [error, setError] = useState("");

  const reportError = useCallback((err) => {
    setError(err.message || String(err));
    setTimeout(() => setError(""), 12000);
  }, []);

  // -- Upload -------------------------------------------------------
  const handleUpload = async (file) => {
    setUploading(true);
    setError("");

    try {
      const result = await api.uploadPresentation(file);
      setTotalSlides(result.slides || 0);
      setDeckLoaded(true);

      const speedResult = await api.getSpeechSpeed();
      setSpeed(speedResult.speed);
    } catch (err) {
      reportError(err);
    } finally {
      setUploading(false);
    }
  };

  // -- Transport ------------------------------------------------------
  const handleStart = async () => {
    try {
      await api.startPresentation(false);
    } catch (err) {
      reportError(err);
    }
  };

  const handleContinue = async () => {
    try {
      await api.startPresentation(true);
    } catch (err) {
      reportError(err);
    }
  };

  const handleStop = async () => {
    try {
      await api.stopPresentation();
    } catch (err) {
      reportError(err);
    }
  };

  const handlePlayPause = async () => {
    try {
      if (paused) {
        await api.resumePresentation();
        setPaused(false);
      } else {
        await api.pausePresentation();
        setPaused(true);
      }
    } catch (err) {
      reportError(err);
    }
  };

  const handleSeekBack = async () => {
    try {
      await api.seekBack();
    } catch (err) {
      reportError(err);
    }
  };

  const handleSeekForward = async () => {
    try {
      await api.seekForward();
    } catch (err) {
      reportError(err);
    }
  };

  const handlePrevSlide = async () => {
    try {
      await api.previousSlide();
    } catch (err) {
      reportError(err);
    }
  };

  const handleNextSlide = async () => {
    try {
      await api.nextSlide();
    } catch (err) {
      reportError(err);
    }
  };

  // -- Tempo ------------------------------------------------------------
  const handleSpeedChange = async (newSpeed) => {
    setSpeed(newSpeed);

    try {
      await api.setSpeechSpeed(newSpeed);
    } catch (err) {
      reportError(err);
    }
  };

  // -- Intercom -----------------------------------------------------------
  const handleAsk = async (question) => {
    setAsking(true);

    try {
      const result = await api.askQuestion(question);

      if (result.mode === "standalone") {
        setHistory((prev) => [...prev, { user: question, assistant: result.answer }]);
      }
    } catch (err) {
      reportError(err);
    } finally {
      setAsking(false);
    }
  };

  // -- Polling: presentation status ------------------------------------
  useEffect(() => {
    if (!deckLoaded) return;

    let cancelled = false;

    const poll = async () => {
      try {
        const s = await api.getPresentationStatus();
        if (cancelled) return;

        setStatus(s.status);
        setPaused(s.paused);
        setAudioError(s.audio_error || "");
        setCurrentSlide(s.current_slide);
        if (s.total_slides) setTotalSlides(s.total_slides);
      } catch {
        // transient — don't spam the error banner for polling misses
      }
    };

    poll();
    const interval = setInterval(poll, STATUS_POLL_MS);

    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [deckLoaded]);

  // -- Polling: live subtitle -------------------------------------------
  useEffect(() => {
    if (!deckLoaded) return;

    let cancelled = false;

    const poll = async () => {
      try {
        const s = await api.getSubtitle();
        if (!cancelled) {
          setSubtitle(s.text || "");
          setSubtitleMode(s.mode || "narration");
        }
      } catch {
        // transient — ignore
      }
    };

    poll();
    const interval = setInterval(poll, SUBTITLE_POLL_MS);

    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [deckLoaded]);

  // -- Polling: chat history --------------------------------------------
  useEffect(() => {
    if (!deckLoaded) return;

    let cancelled = false;

    const poll = async () => {
      try {
        const h = await api.getChatHistory();
        if (!cancelled) setHistory(h || []);
      } catch {
        // transient — ignore
      }
    };

    poll();
    const interval = setInterval(poll, HISTORY_POLL_MS);

    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [deckLoaded]);

  return (
    <div className="console">
      {deckLoaded && (
        <StatusBar status={status} currentSlide={currentSlide} totalSlides={totalSlides} />
      )}

      {error && <div className="error-banner">{error}</div>}

      {deckLoaded && audioError && (
        <div className="error-banner">
          No sound: {audioError}. Captions still play. Run check_audio.py in the backend folder to find out why.
        </div>
      )}

      {!deckLoaded ? (
        <UploadPanel onUpload={handleUpload} uploading={uploading} />
      ) : (
        <>
          <Player
            status={status}
            paused={paused}
            currentSlide={currentSlide}
            totalSlides={totalSlides}
            subtitle={subtitle}
            subtitleMode={subtitleMode}
            speed={speed}
            onStart={handleStart}
            onContinue={handleContinue}
            onStop={handleStop}
            onPlayPause={handlePlayPause}
            onSeekBack={handleSeekBack}
            onSeekForward={handleSeekForward}
            onPrevSlide={handlePrevSlide}
            onNextSlide={handleNextSlide}
            onSpeedChange={handleSpeedChange}
          />

          <IntercomPanel history={history} onAsk={handleAsk} asking={asking} />
        </>
      )}
    </div>
  );
}
