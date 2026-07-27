import React, { useRef, useState } from 'react';
import './SearchBar.css';

function SearchBar({
  searchQuery,
  setSearchQuery,
  searchMode,
  setSearchMode,
  onSearchByText,
  onSearchByImage,
}) {
  const [imagePreview, setImagePreview] = useState(null);
  const [imageFile, setImageFile] = useState(null);
  const fileInputRef = useRef(null);

  const handleTextSubmit = (e) => {
    e.preventDefault();
    onSearchByText(searchQuery);
  };

  const handleFileChange = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setImageFile(file);
    const reader = new FileReader();
    reader.onload = (ev) => setImagePreview(ev.target.result);
    reader.readAsDataURL(file);
  };

  const clearImage = () => {
    setImageFile(null);
    setImagePreview(null);
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const handleImageSubmit = (e) => {
    e.preventDefault();
    onSearchByImage(imageFile);
  };

  return (
    <div className="search-bar">
      <div className="mode-toggle">
        <button
          type="button"
          className={`mode-button ${searchMode === 'text' ? 'active' : ''}`}
          onClick={() => setSearchMode('text')}
        >
          Text
        </button>
        <button
          type="button"
          className={`mode-button ${searchMode === 'image' ? 'active' : ''}`}
          onClick={() => setSearchMode('image')}
        >
          Image
        </button>
      </div>

      {searchMode === 'text' ? (
        <form onSubmit={handleTextSubmit} className="text-search-form">
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search audio & video…"
            className="search-input"
            aria-label="Search audio and video"
          />
          <button type="submit" className="search-button">
            <span className="search-icon">🔍</span>
            <span className="search-text">Search</span>
          </button>
        </form>
      ) : (
        <form onSubmit={handleImageSubmit} className="image-search-form">
          <input
            ref={fileInputRef}
            type="file"
            accept="image/*"
            onChange={handleFileChange}
            className="file-input"
            aria-label="Upload an image"
          />
          {imagePreview && (
            <div className="image-preview">
              <img src={imagePreview} alt="Upload preview" />
              <button type="button" className="clear-button" onClick={clearImage}>
                Clear
              </button>
            </div>
          )}
          <button type="submit" className="search-button" disabled={!imageFile}>
            <span className="search-icon">🔍</span>
            <span className="search-text">Search by image</span>
          </button>
        </form>
      )}
    </div>
  );
}

export default SearchBar;
