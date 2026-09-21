import React, { useCallback, useEffect, useMemo, useState } from 'react';
import Lightbox from 'yet-another-react-lightbox';
import Zoom from 'yet-another-react-lightbox/plugins/zoom';
import 'yet-another-react-lightbox/styles.css';
import ImageGrid from './ImageGrid';
import { itemHref } from '../hooks/useHashRoute';
import { getItem, getSimilar } from '../services/api';
import { titleOf } from '../services/items';
import './ItemDetail.css';

const SIMILAR_COUNT = 24;

const fullImage = (id) => `/images/${id}?size=full`;
const thumbnail = (id) => `/images/${id}?size=thumbnail`;

const hostnameOf = (url) => {
  try {
    return new URL(url).hostname.replace(/^www\./, '');
  } catch {
    return 'the source';
  }
};

const Chevron = ({ direction }) => (
  <svg viewBox="0 0 24 24" aria-hidden="true">
    <path d={direction === 'left' ? 'M15 5l-7 7 7 7' : 'M9 5l7 7-7 7'} />
  </svg>
);

const ExternalLinkIcon = () => (
  <svg viewBox="0 0 24 24" aria-hidden="true">
    <path d="M14 5h5v5M19 5l-8 8M11 7H6a1 1 0 0 0-1 1v10a1 1 0 0 0 1 1h10a1 1 0 0 0 1-1v-5" />
  </svg>
);

function ItemDetail({ id, collection, canGoBack }) {
  const [object, setObject] = useState(null);
  const [currentId, setCurrentId] = useState(id);
  const [similar, setSimilar] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);
  const [zoomIsOpen, setZoomIsOpen] = useState(false);

  const photos = useMemo(() => object?.photos || [], [object]);
  const currentIndex = Math.max(0, photos.findIndex((photo) => photo.id === currentId));
  const current = photos[currentIndex];

  useEffect(() => {
    let isCurrent = true;
    setIsLoading(true);
    setError(null);

    getItem(id)
      .then((loaded) => {
        if (isCurrent) {
          setObject(loaded);
          setCurrentId(id);
        }
      })
      .catch(() => isCurrent && setError('This item could not be found.'))
      .finally(() => isCurrent && setIsLoading(false));

    return () => {
      isCurrent = false;
    };
  }, [id]);

  useEffect(() => {
    let isCurrent = true;
    getSimilar(currentId, SIMILAR_COUNT)
      .then((loaded) => isCurrent && setSimilar(loaded))
      .catch(() => {});
    return () => {
      isCurrent = false;
    };
  }, [currentId]);

  useEffect(() => {
    [photos[currentIndex - 1], photos[currentIndex + 1]].filter(Boolean).forEach((photo) => {
      new Image().src = fullImage(photo.id);
    });
  }, [photos, currentIndex]);

  const showPhoto = useCallback((photoId) => {
    setCurrentId(photoId);
    window.history.replaceState(window.history.state, '', itemHref(photoId));
  }, []);

  const step = useCallback((offset) => {
    const next = photos[currentIndex + offset];
    if (next) {
      showPhoto(next.id);
    }
  }, [photos, currentIndex, showPhoto]);

  useEffect(() => {
    const onKeyDown = (e) => {
      if (zoomIsOpen || e.target.matches('input, textarea')) {
        return;
      }
      if (e.key === 'ArrowLeft') {
        step(-1);
      } else if (e.key === 'ArrowRight') {
        step(1);
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [step, zoomIsOpen]);

  if (error) {
    return (
      <div className="error-message">
        <p>{error}</p>
        <p><a href="#/">Back to the collection</a></p>
      </div>
    );
  }

  if (!current) {
    return (
      <div className="loading-indicator">
        <div className="spinner"></div>
      </div>
    );
  }

  const { metadata } = current;
  const title = titleOf(current);
  const sourceUrl = metadata.source_url;
  const sourceName = collection?.source_name || (sourceUrl && hostnameOf(sourceUrl));
  const license = collection?.license;
  const hasSeveralPhotos = photos.length > 1;

  return (
    <article className={`item-detail ${isLoading ? 'item-detail-loading' : ''}`}>
      <nav className="item-detail-nav">
        {canGoBack ? (
          <>
            <button type="button" className="link-button" onClick={() => window.history.back()}>
              ← Back
            </button>
            <a href="#/">Start over</a>
          </>
        ) : (
          <a href="#/">← Browse the collection</a>
        )}
      </nav>

      <div className="item-detail-main">
        <div className="item-detail-viewer">
          <div className="item-detail-stage">
            <button
              type="button"
              className="item-detail-image"
              onClick={() => setZoomIsOpen(true)}
              aria-label="View larger"
            >
              <img src={fullImage(current.id)} alt={title || 'Uncatalogued image'} />
            </button>
            {hasSeveralPhotos && (
              <>
                <button
                  type="button"
                  className="item-detail-step item-detail-step-previous"
                  onClick={() => step(-1)}
                  disabled={currentIndex === 0}
                  aria-label="Previous photo"
                >
                  <Chevron direction="left" />
                </button>
                <button
                  type="button"
                  className="item-detail-step item-detail-step-next"
                  onClick={() => step(1)}
                  disabled={currentIndex === photos.length - 1}
                  aria-label="Next photo"
                >
                  <Chevron direction="right" />
                </button>
              </>
            )}
          </div>

          {hasSeveralPhotos && (
            <div className="item-detail-photos">
              <p>
                {photos.length} photos of this object. Showing photo {currentIndex + 1}.
              </p>
              <ul>
                {photos.map((photo, index) => (
                  <li key={photo.id}>
                    <a
                      href={itemHref(photo.id)}
                      className={photo.id === current.id ? 'is-current' : ''}
                      aria-current={photo.id === current.id ? 'true' : undefined}
                      aria-label={`Photo ${index + 1} of ${photos.length}`}
                      onClick={(e) => {
                        e.preventDefault();
                        showPhoto(photo.id);
                      }}
                    >
                      <img src={thumbnail(photo.id)} alt="" loading="lazy" />
                    </a>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>

        <div className="item-detail-facts">
          <h2>{title || 'Uncatalogued image'}</h2>

          {!title && (
            <p className="item-detail-note">
              This image has no catalog record. It can be found here because the search
              looks at the picture itself, not at its description.
            </p>
          )}

          {sourceUrl && (
            <a className="item-detail-source" href={sourceUrl} target="_blank" rel="noopener noreferrer">
              <span>View the full record at {sourceName}</span>
              <ExternalLinkIcon />
            </a>
          )}

          <dl>
            {current.object_id !== current.id && (
              <>
                <dt>Object</dt>
                <dd>{current.object_id}</dd>
              </>
            )}
            {metadata.width && metadata.height && (
              <>
                <dt>Original size</dt>
                <dd>{metadata.width.toLocaleString()} × {metadata.height.toLocaleString()} px</dd>
              </>
            )}
            <dt>File</dt>
            <dd>{metadata.file_name}</dd>
          </dl>

          {license && (
            <p className="item-detail-license">
              {license.url ? (
                <a href={license.url} target="_blank" rel="noopener noreferrer">{license.name}</a>
              ) : license.name}
              {license.note ? ` — ${license.note}` : ''}
            </p>
          )}
        </div>
      </div>

      {similar.length > 0 && (
        <section>
          <h3>Looks similar</h3>
          <p className="item-detail-note">
            Chosen by an AI model from how the pictures look, not from the catalog.
            Follow any of them to keep wandering.
          </p>
          <ImageGrid items={similar} />
        </section>
      )}

      <Lightbox
        open={zoomIsOpen}
        close={() => setZoomIsOpen(false)}
        index={currentIndex}
        slides={photos.map((photo) => ({ src: fullImage(photo.id), alt: title || '' }))}
        on={{ view: ({ index }) => photos[index] && showPhoto(photos[index].id) }}
        plugins={[Zoom]}
        carousel={{ finite: true }}
      />
    </article>
  );
}

export default ItemDetail;
