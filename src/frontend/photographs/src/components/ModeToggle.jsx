import React from 'react';
import './ModeToggle.css';

const MODES = [
  ['auto', 'Auto'],
  ['visual', 'Appearance'],
  ['keyword', 'Catalog'],
];

const READINGS = {
  identifier: 'catalog number',
  field: 'field',
  phrase: 'phrase',
  name: 'name',
  date: 'date',
  place: 'place',
  topic: 'subject',
  object_type: 'object',
  description: 'description',
};

function ModeToggle({ mode, onChange, reading }) {
  const readAs = mode === 'auto' && reading ? READINGS[reading.kind] : null;

  return (
    <div className="mode-toggle" role="radiogroup" aria-label="Search by">
      <span className="mode-toggle-label">Search by</span>
      {MODES.map(([value, label]) => (
        <button
          key={value}
          type="button"
          role="radio"
          aria-checked={mode === value}
          className={mode === value ? 'is-active' : ''}
          title={value === 'auto' && readAs ? reading.message : undefined}
          onClick={() => mode !== value && onChange(value)}
        >
          {label}
          {value === 'auto' && readAs && <span className="mode-toggle-reading"> · {readAs}</span>}
        </button>
      ))}
    </div>
  );
}

export default ModeToggle;
