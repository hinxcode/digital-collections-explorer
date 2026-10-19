import React, { useEffect, useRef } from 'react';
import './GroupFilter.css';

function GroupFilter({
  groups, label, selected, onChange, counts,
}) {
  const panel = useRef(null);

  useEffect(() => {
    const closeOutside = (event) => {
      if (panel.current?.open && !panel.current.contains(event.target)) {
        panel.current.open = false;
      }
    };
    const closeOnEscape = (event) => {
      if (event.key === 'Escape' && panel.current?.open) {
        panel.current.open = false;
        panel.current.querySelector('summary')?.focus();
      }
    };
    document.addEventListener('click', closeOutside);
    document.addEventListener('keydown', closeOnEscape);
    return () => {
      document.removeEventListener('click', closeOutside);
      document.removeEventListener('keydown', closeOnEscape);
    };
  }, []);

  if (!groups || groups.length < 2) {
    return null;
  }

  const every = groups.map((group) => group.id);
  const chosen = selected.length > 0 ? every.filter((id) => selected.includes(id)) : every;
  const showsAll = chosen.length === every.length;
  const choose = (ids) => onChange(ids.length === every.length ? [] : ids);
  const toggle = (id) => choose(chosen.includes(id)
    ? chosen.filter((other) => other !== id)
    : every.filter((other) => other === id || chosen.includes(other)));

  let summary = `${chosen.length} of ${every.length}`;
  if (showsAll) {
    summary = 'All';
  } else if (chosen.length === 1) {
    summary = groups.find((group) => group.id === chosen[0]).label;
  }

  return (
    <details className="group-filter" ref={panel}>
      <summary>
        <span className="group-filter-name">{label || 'Group'}</span>
        <span className="group-filter-summary">{summary}</span>
      </summary>
      <div className="group-filter-panel">
        <ul>
          {groups.map((group) => (
            <li key={group.id}>
              <label>
                <input
                  type="checkbox"
                  checked={chosen.includes(group.id)}
                  disabled={chosen.length === 1 && chosen[0] === group.id}
                  onChange={() => toggle(group.id)}
                />
                <span>{group.label}</span>
                {counts && (
                  <span className="group-filter-count">
                    {(counts[group.id] || 0).toLocaleString()}
                  </span>
                )}
              </label>
              <button type="button" onClick={() => choose([group.id])}>
                only
              </button>
            </li>
          ))}
        </ul>
        <button
          type="button"
          className="group-filter-all"
          onClick={() => choose(every)}
          disabled={showsAll}
        >
          Show all
        </button>
      </div>
    </details>
  );
}

export default GroupFilter;
