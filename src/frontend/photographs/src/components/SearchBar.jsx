import React, { useState } from 'react';
import './SearchBar.css';
import FilterBar from './FilterBar';

function SearchBar({
  inputRef,
  searchMode,
  setSearchMode,
  searchQuery,
  setSearchQuery,
  uploadedImage,
  setUploadedImage,
  filepathSearchTerm,
  setFilepathSearchTerm,
  onSearchByText,
  onSearchByImage,
  onSearchByDate,
  searchNearDate,
  setSearchNearDate,
}) {
  const [previewUrl, setPreviewUrl] = useState(null);

  const handleSubmit = (e) => {
    e.preventDefault();
    
    if (searchMode === 'text') {
      onSearchByText(searchQuery, filepathSearchTerm);
    } else if (searchMode === 'image' && uploadedImage) {
      onSearchByImage(uploadedImage);
    } else if (searchMode === 'date') {
      onSearchByDate(searchQuery, searchNearDate);
    }
  };

  const handleImageChange = (e) => {
    const file = e.target.files[0];
    if (!file) return;

    setUploadedImage(file);
    
    // Create a preview URL for the uploaded image
    const reader = new FileReader();
    reader.onloadend = () => {
      setPreviewUrl(reader.result);
    };
    reader.readAsDataURL(file);
  };

  const clearImage = () => {
    setUploadedImage(null);
    setPreviewUrl(null);

    if (document.getElementById('image-upload')) {
      document.getElementById('image-upload').value = '';
    }
  };

  const switchMode = (mode) => {
    if (mode === searchMode) return;
    setSearchMode(mode);

    if (mode !== 'image') {
      clearImage();
    } 
    setSearchQuery('');
    
  };

  return (
    <div className="search-bar">
      <div className="search-mode-selector">
        <button 
          className={`mode-button ${searchMode === 'text' ? 'active' : ''}`}
          onClick={() => switchMode('text')}
          type="button"
        >
          Text Search
        </button>
        <button 
          className={`mode-button ${searchMode === 'image' ? 'active' : ''}`}
          onClick={() => switchMode('image')}
          type="button"
        >
          Image Search
        </button>
        <button 
          className={`mode-button ${searchMode === 'date' ? 'active' : ''}`}
          onClick={() => switchMode('date')}
          type="button"
        >
          Date Search
        </button>
      </div>

      <form onSubmit={handleSubmit}>
        {searchMode === 'text' ? (
          <div className="vertical-stack">
            <div className="image-search-container">
              <input
                ref={inputRef}
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search historical photographs..."
                className="search-input"
                aria-label="Search photographs"
              />
              <button type="submit" className="search-button" disabled={!searchQuery}>
                <span className="search-icon">🔍</span>
                <span className="search-text">Search</span>
              </button>
            </div>
            <FilterBar 
              filepathSearchTerm={filepathSearchTerm}
              setFilepathSearchTerm={setFilepathSearchTerm}
            />
          </div>
          
        ) : (searchMode === 'image' ? (
          <div className="image-search-container">
            {!previewUrl ? (
              <div className="image-upload">
                <input
                  type="file"
                  accept="image/*"
                  onChange={handleImageChange}
                  id="image-upload"
                  className="image-input"
                />
                <label htmlFor="image-upload" className="image-upload-label">
                  <span className="upload-icon">📷</span>
                  <span>Select an image or drag & drop</span>
                </label>
              </div>
            ) : (
              <div className="image-preview-container">
                <img src={previewUrl} alt="Preview" className="image-preview" />
                <button 
                  type="button"
                  className="clear-image-button"
                  onClick={clearImage}
                >
                  ✕
                </button>
              </div>
            )}
            <button 
              type="submit" 
              className="search-button"
              disabled={!uploadedImage}
            >
              <span className="search-icon">🔍</span>
              <span className="search-text">Find Similar</span>
            </button>
          </div>
        ) : (
          <>
            <div className="date-search-block">
              <input
                ref={inputRef}
                type="date"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search historical photographs..."
                className="search-input"
                aria-label="Search photographs"
              />
              <div className="near-date-checkbox-container">
                <input
                  type="checkbox"
                  checked={searchNearDate}
                  onChange={(e) => setSearchNearDate(e.target.checked)}
                  id="near-date-checkbox"
                  className="include-near-date"
                  aria-label="Include photographs taken near this date"
                />
                <label htmlFor="near-date-checkbox">Include records from near the selected date?</label>
              </div>
            </div>
            <button type="submit" className="search-button" disabled={!searchQuery}>
              <span className="search-icon">🔍</span>
              <span className="search-text">Search</span>
            </button>
          </>
        ))}
      </form>

      {searchMode === 'text' && (
        <div className="search-suggestions">
          <p>
            Try searching for: "city streets" or "people in uniform"
          </p>
        </div>
      )}
    </div>
  );
}

export default SearchBar;
