import React, { useEffect, useRef, useState } from 'react';
import './SearchBar.css';

const SearchIcon = () => (
  <svg viewBox="0 0 24 24" aria-hidden="true">
    <circle cx="11" cy="11" r="7" />
    <path d="M16.5 16.5 21 21" />
  </svg>
);

const CameraIcon = () => (
  <svg viewBox="0 0 24 24" aria-hidden="true">
    <path d="M4 8h3l1.6-2.5h6.8L17 8h3a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V9a1 1 0 0 1 1-1Z" />
    <circle cx="12" cy="13.2" r="3.4" />
  </svg>
);

const CloseIcon = () => (
  <svg viewBox="0 0 24 24" aria-hidden="true">
    <path d="M6 6l12 12M18 6 6 18" />
  </svg>
);

const NARROW_SCREEN = '(max-width: 600px)';
const PLACEHOLDER = 'Describe what you are looking for, in your own words';
const SHORT_PLACEHOLDER = 'Describe what you want to see';

// The full hint does not fit a phone, where it would be cut off mid-word.
const usePlaceholder = () => {
  const [isNarrow, setIsNarrow] = useState(() => window.matchMedia(NARROW_SCREEN).matches);

  useEffect(() => {
    const query = window.matchMedia(NARROW_SCREEN);
    const onChange = (e) => setIsNarrow(e.matches);
    query.addEventListener('change', onChange);
    return () => query.removeEventListener('change', onChange);
  }, []);

  return isNarrow ? SHORT_PLACEHOLDER : PLACEHOLDER;
};

const imageFrom = (fileList) => (
  Array.from(fileList || []).find((file) => file.type.startsWith('image/')) || null
);

/**
 * One field for both kinds of search: type a description, or give it a picture
 * by choosing, dropping or pasting one.
 */
function SearchBar({
  inputRef,
  searchQuery,
  setSearchQuery,
  uploadedImage,
  onSearchByText,
  onSearchByImage,
  onClearImage,
}) {
  const [previewUrl, setPreviewUrl] = useState(null);
  const [isDraggingOver, setIsDraggingOver] = useState(false);
  const fileInputRef = useRef(null);
  const placeholder = usePlaceholder();

  useEffect(() => {
    if (!uploadedImage) {
      setPreviewUrl(null);
      return undefined;
    }
    const url = URL.createObjectURL(uploadedImage);
    setPreviewUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [uploadedImage]);

  const handleSubmit = (e) => {
    e.preventDefault();
    onSearchByText(searchQuery);
  };

  const handleFileChosen = (e) => {
    const image = imageFrom(e.target.files);
    if (image) {
      onSearchByImage(image);
    }
    e.target.value = '';
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setIsDraggingOver(false);
    const image = imageFrom(e.dataTransfer.files);
    if (image) {
      onSearchByImage(image);
    }
  };

  const handlePaste = (e) => {
    const image = imageFrom(e.clipboardData.files);
    if (image) {
      e.preventDefault();
      onSearchByImage(image);
    }
  };

  return (
    <div className="search-bar">
      <form
        className={`search-field ${isDraggingOver ? 'search-field-dragging' : ''}`}
        role="search"
        onSubmit={handleSubmit}
        onDragOver={(e) => { e.preventDefault(); setIsDraggingOver(true); }}
        onDragLeave={() => setIsDraggingOver(false)}
        onDrop={handleDrop}
      >
        <input
          ref={inputRef}
          type="search"
          className="search-input"
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          onPaste={handlePaste}
          placeholder={placeholder}
          aria-label="Search the collection"
          enterKeyHint="search"
        />
        <button
          type="button"
          className="search-field-button"
          onClick={() => fileInputRef.current?.click()}
          aria-label="Search with an image"
          title="Search with an image. You can also drop or paste one here."
        >
          <CameraIcon />
        </button>
        <button
          type="submit"
          className={`search-submit ${searchQuery.trim() ? 'search-submit-ready' : ''}`}
          aria-label="Search"
          title="Search"
        >
          <SearchIcon />
        </button>
        <input
          ref={fileInputRef}
          type="file"
          accept="image/*"
          className="search-file-input"
          onChange={handleFileChosen}
          tabIndex={-1}
          aria-hidden="true"
        />
      </form>

      {isDraggingOver && <p className="search-hint">Drop the image to find ones like it</p>}

      {previewUrl && !isDraggingOver && (
        <div className="search-image-chip">
          <img src={previewUrl} alt="" />
          <span>Showing images like this one</span>
          <button type="button" onClick={onClearImage} aria-label="Remove the image">
            <CloseIcon />
          </button>
        </div>
      )}
    </div>
  );
}

export default SearchBar;
