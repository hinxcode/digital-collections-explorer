import React from 'react';
import './ModeToggle.css';

const MODES = [
  ['auto', 'Auto'],
  ['visual', 'Appearance'],
  ['keyword', 'Catalog'],
];

function ModeToggle({ mode, onChange }) {
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
          onClick={() => mode !== value && onChange(value)}
        >
          {label}
        </button>
      ))}
    </div>
  );
}

export default ModeToggle;
