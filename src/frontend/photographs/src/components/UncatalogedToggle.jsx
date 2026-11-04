import React from 'react';
import './UncatalogedToggle.css';

function UncatalogedToggle({ collection, catalogedOnly, onChange }) {
  const count = collection?.uncataloged_images || 0;
  if (!count || count >= collection.images) {
    return null;
  }

  return (
    <label
      className="uncataloged-toggle"
      title={`Leave out the ${count.toLocaleString()} images that have no catalog record. Only a search by appearance can find them.`}
    >
      <span>With catalog records only</span>
      <input
        type="checkbox"
        role="switch"
        checked={catalogedOnly}
        onChange={(event) => onChange(event.target.checked)}
      />
      <span className="uncataloged-toggle-track" aria-hidden="true" />
    </label>
  );
}

export default UncatalogedToggle;
