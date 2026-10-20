import React from 'react';
import { searchHref } from '../hooks/useHashRoute';
import './SearchNotice.css';

function SearchNotice({
  search, query, groups, mode,
}) {
  const { correction, keyword } = search;
  if (!correction && !keyword?.empty) {
    return null;
  }

  return (
    <div className="search-notice">
      {correction && (
        <p>
          Showing results for <strong>{correction.to}</strong>
          {' · '}
          <a href={searchHref(query, 1, groups, { mode, exact: true })}>
            Search instead for “{correction.from}”
          </a>
        </p>
      )}
      {keyword?.empty && <p className="search-notice-empty">{keyword.empty.message}</p>}
    </div>
  );
}

export default SearchNotice;
