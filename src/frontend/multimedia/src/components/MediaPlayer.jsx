import React from 'react';
import { getMediaUrl, getImageUrl, getDownloadUrl } from '../services/api';
import './MediaPlayer.css';

const MediaPlayer = ({ item, onClose }) => {
  const mediaSrc = getMediaUrl(item.id);

  return (
    <div className="media-player">
      <div className="media-player-header">
        <h3 className="media-player-title" title={item.file_name}>
          {item.file_name}
        </h3>
        <button className="media-close-button" onClick={onClose} aria-label="Close">
          ✕
        </button>
      </div>

      <div className="media-player-body">
        {item.type === 'video' ? (
          <video
            className="media-video"
            src={mediaSrc}
            poster={getImageUrl(item.id, 'full')}
            controls
            autoPlay
          />
        ) : item.type === 'audio' ? (
          <div className="media-audio-wrap">
            <img
              className="media-waveform"
              src={getImageUrl(item.id, 'full')}
              alt={`${item.file_name} waveform`}
            />
            <audio className="media-audio" src={mediaSrc} controls autoPlay />
          </div>
        ) : (
          <img
            className="media-image"
            src={getImageUrl(item.id, 'full')}
            alt={item.file_name}
          />
        )}
      </div>

      <div className="media-player-footer">
        <span className="media-player-score">
          Similarity score: {item.score.toFixed(4)}
        </span>
        <a
          href={getDownloadUrl(item.id)}
          target="_blank"
          rel="noopener noreferrer"
          className="media-download-button"
        >
          Download
        </a>
      </div>
    </div>
  );
};

export default MediaPlayer;
