import React from 'react';
import { itemHref } from '../hooks/useHashRoute';
import { titleOf } from '../services/items';
import './ImageGrid.css';

// Used when an index does not record image dimensions.
const FALLBACK_ASPECT_RATIO = 3 / 2;

// Very wide or very tall images would otherwise distort a whole row.
const MIN_ASPECT_RATIO = 0.5;
const MAX_ASPECT_RATIO = 2.4;

const aspectRatioOf = (item) => {
  const { width, height } = item.metadata || {};
  const ratio = width && height ? width / height : FALLBACK_ASPECT_RATIO;
  return Math.min(MAX_ASPECT_RATIO, Math.max(MIN_ASPECT_RATIO, ratio));
};

const ImageGrid = React.memo(({ items, size = 'regular' }) => (
  <ul className={`image-grid image-grid-${size}`}>
    {items.map((item) => {
      const title = titleOf(item);
      const extraImages = (item.image_count || 1) - 1;

      return (
        <li key={item.id} className="image-grid-cell" style={{ '--ratio': aspectRatioOf(item) }}>
          <a href={itemHref(item.id)} aria-label={title || 'Uncatalogued image'}>
            <img src={`/images/${item.id}?size=thumbnail`} alt={title || ''} loading="lazy" />
            <span className="image-grid-caption">{title || 'Uncatalogued image'}</span>
            {extraImages > 0 && (
              <span className="image-grid-badge" title={`${extraImages} more photos of this object`}>
                +{extraImages}
              </span>
            )}
          </a>
        </li>
      );
    })}
  </ul>
));

export default ImageGrid;
