import React from 'react';
import './UncatalogedToggle.css';

function UncatalogedToggle({ collection, checked, onChange }) {
  const count = collection?.uncataloged_images || 0;
  if (!count || count >= collection.images) {
    return null;
  }

  return (
    <label
      className="uncataloged-toggle"
      title={`${count.toLocaleString()} images have no catalog record. Only a search by appearance can find them.`}
    >
      <span>Images without catalog records</span>
      <input
        type="checkbox"
        role="switch"
        checked={checked}
        onChange={(event) => onChange(event.target.checked)}
      />
      <span className="uncataloged-toggle-track" aria-hidden="true" />
    </label>
  );
}

export default UncatalogedToggle;
