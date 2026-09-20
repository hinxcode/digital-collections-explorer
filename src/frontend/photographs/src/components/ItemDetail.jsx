import React, { useEffect, useState } from 'react';
import Lightbox from 'yet-another-react-lightbox';
import Zoom from 'yet-another-react-lightbox/plugins/zoom';
import 'yet-another-react-lightbox/styles.css';
import ImageGrid from './ImageGrid';
import { getItem, getSimilar } from '../services/api';
import { titleOf } from '../services/items';
import './ItemDetail.css';

const SIMILAR_COUNT = 24;

const hostnameOf = (url) => {
  try {
    return new URL(url).hostname.replace(/^www\./, '');
  } catch {
    return 'the source';
  }
};

function ItemDetail({ id, collection }) {
  const [item, setItem] = useState(null);
  const [similar, setSimilar] = useState([]);
  const [error, setError] = useState(null);
  const [zoomIsOpen, setZoomIsOpen] = useState(false);

  useEffect(() => {
    let isCurrent = true;
    setItem(null);
    setSimilar([]);
    setError(null);

    getItem(id)
      .then((loaded) => isCurrent && setItem(loaded))
      .catch(() => isCurrent && setError('This item could not be found.'));
    getSimilar(id, SIMILAR_COUNT)
      .then((loaded) => isCurrent && setSimilar(loaded))
      .catch(() => isCurrent && setSimilar([]));

    return () => {
      isCurrent = false;
    };
  }, [id]);

  if (error) {
    return (
      <div className="error-message">
        <p>{error}</p>
        <p><a href="#/">Back to the collection</a></p>
      </div>
    );
  }

  if (!item) {
    return (
      <div className="loading-indicator">
        <div className="spinner"></div>
      </div>
    );
  }

  const { metadata } = item;
  const title = titleOf(item);
  const sourceUrl = metadata.source_url;
  const sourceName = collection?.source_name || (sourceUrl && hostnameOf(sourceUrl));
  const license = collection?.license;
  const fullImage = `/images/${item.id}?size=full`;

  return (
    <article className="item-detail">
      <nav className="item-detail-nav">
        <button type="button" className="link-button" onClick={() => window.history.back()}>
          ← Back
        </button>
        <a href="#/">Start over</a>
      </nav>

      <div className="item-detail-main">
        <button
          type="button"
          className="item-detail-image"
          onClick={() => setZoomIsOpen(true)}
          aria-label="View larger"
        >
          <img src={fullImage} alt={title || 'Uncatalogued image'} />
        </button>

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
              View the full record at {sourceName} ↗
            </a>
          )}

          <dl>
            {item.object_id !== item.id && (
              <>
                <dt>Object</dt>
                <dd>{item.object_id}</dd>
              </>
            )}
            {item.image_count > 1 && (
              <>
                <dt>Photos of this object</dt>
                <dd>{item.image_count}</dd>
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

      {item.same_object.length > 0 && (
        <section>
          <h3>More photos of this object</h3>
          <ImageGrid items={item.same_object} size="small" />
        </section>
      )}

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
        slides={[{ src: fullImage, alt: title || '' }]}
        plugins={[Zoom]}
        carousel={{ finite: true }}
        render={{ buttonPrev: () => null, buttonNext: () => null }}
      />
    </article>
  );
}

export default ItemDetail;
