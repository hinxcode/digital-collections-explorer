import React from 'react';
import { LazyLoadImage } from 'react-lazy-load-image-component';
import 'react-lazy-load-image-component/src/effects/blur.css';
import { getImageUrl } from '../services/api';
import './MediaCard.css';

const TYPE_BADGE = {
  video: { icon: '🎬', label: 'Video' },
  audio: { icon: '🔊', label: 'Audio' },
  image: { icon: '🖼️', label: 'Image' },
};

const MediaCard = ({ item, onClick }) => {
  const badge = TYPE_BADGE[item.type] || { icon: '📄', label: item.type };

  return (
    <div className="media-card" onClick={onClick}>
      <div className="media-thumb-container">
        <LazyLoadImage
          alt={item.file_name}
          effect="blur"
          src={getImageUrl(item.id, 'thumbnail')}
          width="100%"
        />
        <span className="media-type-badge">
          {badge.icon} {badge.label}
        </span>
        {item.type === 'video' && <span className="media-play-icon">▶</span>}
      </div>

      <div className="media-card-content">
        <h3 className="media-card-title" title={item.file_name}>
          {item.file_name}
        </h3>
        <div className="media-card-meta">
          <span className="media-score">score {item.score.toFixed(3)}</span>
        </div>
      </div>
    </div>
  );
};

export default MediaCard;
