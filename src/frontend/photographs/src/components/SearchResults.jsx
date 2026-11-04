import React from 'react';
import ImageGrid from './ImageGrid';
import Pagination from './Pagination';
import './SearchResults.css';

const SearchResults = React.memo(({
  items,
  isLoading,
  error,
  currentPage,
  setCurrentPage,
  hasMore,
  heading,
  groupLabels,
  notice,
}) => {
  if (isLoading) {
    return (
      <div className="loading-indicator">
        <div className="spinner"></div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="error-message">
        <p>{error}</p>
      </div>
    );
  }

  if (items.length === 0) {
    return (
      <div className="gallery-container">
        {notice}
        <div className="no-results">
          <p>Nothing matched. Try describing what the picture looks like.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="gallery-container">
      <h2 className="visually-hidden">{heading}</h2>
      {notice}
      <ImageGrid items={items} groupLabels={groupLabels} />
      <Pagination
        currentPage={currentPage}
        setCurrentPage={setCurrentPage}
        hasMore={hasMore}
        isLoading={isLoading}
      />
    </div>
  );
});

export default SearchResults;
