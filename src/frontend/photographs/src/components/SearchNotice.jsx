import React from 'react';
import { searchHref } from '../hooks/useHashRoute';
import './SearchNotice.css';

const READINGS = {
  identifier: 'a catalog number',
  field: 'a field search',
  phrase: 'an exact phrase',
  name: 'a name',
  date: 'a date',
  place: 'a place',
  topic: 'a subject',
  object_type: 'a kind of object',
};

const readingOf = (search) => {
  const reading = READINGS[search?.kind];
  if (!reading) {
    return null;
  }
  return search.matched?.whole === false ? `Mentions ${reading}` : `Read as ${reading}`;
};

function SearchNotice({
  search, query, groups, mode, uncataloged = true,
}) {
  const { correction, keyword } = search;
  const reading = mode === 'auto' ? readingOf(search) : null;
  if (!correction && !reading && !keyword?.empty) {
    return null;
  }

  return (
    <div className="search-notice">
      {correction && (
        <p>
          Showing results for <strong>{correction.to}</strong>
          {' · '}
          <a href={searchHref(query, 1, groups, { mode, exact: true, uncataloged })}>
            Search instead for “{correction.from}”
          </a>
        </p>
      )}
      {reading && <p className="search-notice-note" title={search.message}>{reading}</p>}
      {keyword?.empty && <p className="search-notice-note">{keyword.empty.message}</p>}
    </div>
  );
}

export default SearchNotice;
