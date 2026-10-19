import React from 'react';
import { searchHref } from '../hooks/useHashRoute';
import './SearchNotice.css';

// How many groups the distribution line names before "and N more".
const SHOWN_GROUPS = 3;

const BACK_TO_AUTO = {
  visual: 'Use the catalog too',
  keyword: 'Use appearance too',
  hybrid: 'Let the site decide',
};

const overrides = ({ weights }, mode) => {
  if (mode !== 'auto') {
    return [['auto', BACK_TO_AUTO[mode]]];
  }
  if (weights.visual < weights.keyword) {
    return [['visual', 'Search by appearance instead']];
  }
  if (weights.keyword < weights.visual) {
    return [['keyword', 'Search the catalog instead']];
  }
  return [['visual', 'Appearance only'], ['keyword', 'Catalog only']];
};

const spreadOf = (results, groupLabels) => {
  const counts = new Map();
  results.forEach(({ metadata }) => {
    const label = groupLabels[metadata?.group];
    if (label) {
      counts.set(label, (counts.get(label) || 0) + 1);
    }
  });
  return [...counts.entries()].sort((a, b) => b[1] - a[1]);
};

const describeSpread = (spread, groupLabel) => {
  const shown = spread.slice(0, SHOWN_GROUPS).map(([label, count]) => `${label} (${count})`);
  const rest = spread.length - shown.length;
  if (rest > 0) {
    return `From ${shown.join(', ')} and ${rest} more ${(groupLabel || 'group').toLowerCase()}${rest > 1 ? 's' : ''}`;
  }
  return `From ${shown.slice(0, -1).join(', ')} and ${shown[shown.length - 1]}`;
};

function SearchNotice({
  search, query, groups, mode, exact, results, groupLabels, groupLabel,
}) {
  const { correction, keyword } = search;
  const spread = mode === 'keyword' ? [] : spreadOf(results, groupLabels);

  return (
    <div className="search-notice">
      {correction && (
        <p className="search-notice-spelling">
          Showing results for <strong>{correction.to}</strong>
          {' · '}
          <a href={searchHref(query, 1, groups, { mode, exact: true })}>
            Search instead for “{correction.from}”
          </a>
        </p>
      )}
      <p className="search-notice-reading">
        {search.message}
        {overrides(search, mode).map(([target, label]) => (
          <React.Fragment key={target}>
            {' · '}
            <a href={searchHref(query, 1, groups, { mode: target, exact })}>{label}</a>
          </React.Fragment>
        ))}
      </p>
      {keyword?.empty && <p className="search-notice-empty">{keyword.empty.message}</p>}
      {spread.length > 1 && (
        <p className="search-notice-spread">{describeSpread(spread, groupLabel)}</p>
      )}
    </div>
  );
}

export default SearchNotice;
