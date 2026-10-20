import React from 'react';
import './ModeToggle.css';

const MODES = [
  ['auto', 'Auto'],
  ['visual', 'Appearance'],
  ['keyword', 'Catalog'],
];

const READINGS = {
  identifier: 'a catalog number',
  field: 'a field search',
  phrase: 'an exact phrase',
  name: 'a name',
  date: 'a date',
  place: 'a place',
  topic: 'a subject',
  object_type: 'a kind of object',
};

const readingOf = (search) => {
  const reading = READINGS[search?.kind];
  if (!reading) {
    return null;
  }
  return search.matched?.whole === false ? `Mentions ${reading}` : `Read as ${reading}`;
};

function ModeToggle({ mode, onChange, reading }) {
  const caption = mode === 'auto' ? readingOf(reading) : null;

  return (
    <>
      <div className="mode-toggle" role="radiogroup" aria-label="Search by">
        <span className="mode-toggle-label">Search by</span>
        {MODES.map(([value, label]) => (
          <button
            key={value}
            type="button"
            role="radio"
            aria-checked={mode === value}
            className={mode === value ? 'is-active' : ''}
            onClick={() => mode !== value && onChange(value)}
          >
            {label}
          </button>
        ))}
      </div>
      <span
        className="mode-toggle-reading"
        title={caption ? reading.message : undefined}
        aria-live="polite"
      >
        {caption}
      </span>
    </>
  );
}

export default ModeToggle;
