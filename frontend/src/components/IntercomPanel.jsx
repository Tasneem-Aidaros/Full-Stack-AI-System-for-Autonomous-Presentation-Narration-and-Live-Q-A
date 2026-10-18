import { useState } from "react";

export default function IntercomPanel({ history, onAsk, asking }) {
  const [value, setValue] = useState("");

  const submit = (e) => {
    e.preventDefault();
    const question = value.trim();
    if (!question) return;
    onAsk(question);
    setValue("");
  };

  return (
    <div className="panel">
      <p className="panel__label">Intercom — Ask the Presenter</p>

      <form className="intercom__input-row" onSubmit={submit}>
        <input
          type="text"
          placeholder="Type a question for the audience…"
          value={value}
          onChange={(e) => setValue(e.target.value)}
        />
        <button className="btn" type="submit" disabled={asking || !value.trim()}>
          Send
        </button>
      </form>

      <div className="intercom__log">
        {history.length === 0 ? (
          <p className="intercom__empty">No questions yet.</p>
        ) : (
          history
            .slice()
            .reverse()
            .map((entry, i) => (
              <div className="intercom__entry" key={i}>
                <p className="intercom__q">Q — {entry.user}</p>
                <p className="intercom__a">{entry.assistant}</p>
              </div>
            ))
        )}
      </div>
    </div>
  );
}
