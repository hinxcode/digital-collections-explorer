import React, { useState } from 'react';
import MediaCard from './MediaCard';
import MediaPlayer from './MediaPlayer';
import './MediaResultsGrid.css';

const MediaResultsGrid = ({ items }) => {
  const [selected, setSelected] = useState(null);

  return (
    <div className="media-results-grid">
      <div className="media-grid-container">
        {items.map((item, index) => (
          <div className="media-grid-item" key={item.id || index}>
            <MediaCard item={item} onClick={() => setSelected(item)} />
          </div>
        ))}
      </div>

      {selected && (
        <div className="media-modal-overlay" onClick={() => setSelected(null)}>
          <div
            className="media-modal-content"
            onClick={(e) => e.stopPropagation()}
          >
            <MediaPlayer item={selected} onClose={() => setSelected(null)} />
          </div>
        </div>
      )}
    </div>
  );
};

export default MediaResultsGrid;
