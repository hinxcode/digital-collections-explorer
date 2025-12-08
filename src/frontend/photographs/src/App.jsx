import React, { useState, useEffect, useCallback, useRef } from 'react';
import SearchBar from './components/SearchBar';
import { ResultsPerPageDropdown } from './components/Pagination';
import SearchResults from './components/SearchResults';
import { searchByText, searchByImage, getEmbeddingStats, searchByDate } from './services/api';
import './App.css';

function App() {
  const [photos, setPhotos] = useState([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [filepathSearchTerm, setFilepathSearchTerm] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);
  const searchInputRef = useRef(null);
  const [searchMode, setSearchMode] = useState('text'); // 'text', 'image', 'date'
  const [uploadedImage, setUploadedImage] = useState(null);
  const [hasMore, setHasMore] = useState(false);
  const [currentPage, setCurrentPage] = useState(1);
  const [resultsPerPage, setResultsPerPage] = useState(50);
  const [searchNearDate, setSearchNearDate] = useState(false);
  const [embeddingCount, setEmbeddingCount] = useState(null);

  useEffect(() => {
    const fetchEmbeddingStats = async () => {
      try {
        const stats = await getEmbeddingStats();
        setEmbeddingCount(stats.count);
      } catch (error) {
        console.error('Failed to load embedding stats:', error);
      }
    };

    fetchEmbeddingStats();
  }, []);

  const formatPhotosForGallery = (results) => {
    return results.map(result => ({
      src: `/images/${result.id}?size=full`,
      thumbnail: `/images/${result.id}?size=thumbnail`,
      thumbnailWidth: 320, // Default width if not available
      thumbnailHeight: 212, // Default height with 3:2 aspect ratio
      width: 800, // Default width for lightbox
      height: 600, // Default height for lightbox
      alt: result.metadata.file_name || '',
      originalData: result,
      customOverlay: (
        <div className="custom-overlay">
          <div className="custom-overlay-title">
            {result.metadata.file_name || result.file_name || 'Untitled'}
          </div>
        </div>
      )
    }));
  };

  const handleSearchByText = useCallback(async (query, filepathSearchTerm) => {
    if (!query.trim()) {
      setError('Please enter a search term');
      return;
    }
    
    setIsLoading(true);
    setError(null);
    setSearchMode('text');
    setSearchQuery(query);
    setFilepathSearchTerm(filepathSearchTerm);
    
    try {
      const results = await searchByText(query, resultsPerPage, currentPage, filepathSearchTerm);
      setPhotos(formatPhotosForGallery(results));
      setHasMore(results.length >= resultsPerPage);
    } catch (error) {
      console.error('Error performing search:', error);
      setError('Text search failed. Please try again.');
    } finally {
      setIsLoading(false);
    }
  }, [resultsPerPage, currentPage]);

  const handleSearchByImage = useCallback(async (image) => {
    setIsLoading(true);
    setError(null);
    setSearchMode('image');
    
    try {
      const results = await searchByImage(image, resultsPerPage, currentPage);
      setPhotos(formatPhotosForGallery(results));
      setHasMore(results.length >= resultsPerPage);
    } catch (error) {
      console.error('Error performing image search:', error);
      setError('Image search failed. Please try again.');
    } finally {
      setIsLoading(false);
    }
  }, [resultsPerPage, currentPage]);

  const handleSearchByDate = useCallback(async (query, searchNearDate) => {
  if (!query.trim()) {
    setError('Please enter a search term');
    return;
  }
  
  setIsLoading(true);
  setError(null);
  setSearchMode('date');
  setSearchQuery(query);
  setSearchNearDate(searchNearDate);
  
  try {
    const results = await searchByDate(query, resultsPerPage, currentPage, searchNearDate);
    setPhotos(formatPhotosForGallery(results));
    setHasMore(results.length >= resultsPerPage);
  } catch (error) {
    console.error('Error performing search:', error);
    setError('Date search failed. Please try again.');
  } finally {
    setIsLoading(false);
  }
}, [resultsPerPage, currentPage]);

  useEffect(() => {
    if (searchMode === 'text' && searchQuery.trim()) {
      handleSearchByText(searchQuery, filepathSearchTerm);
    } else if (searchMode === 'image' && uploadedImage) {
      handleSearchByImage(uploadedImage);
    } else if (searchMode === 'date' && searchQuery.trim()) {
      handleSearchByDate(searchQuery, searchNearDate);
    }
  }, [currentPage, resultsPerPage, searchMode, searchQuery, searchNearDate, uploadedImage, filepathSearchTerm, handleSearchByText, handleSearchByImage, handleSearchByDate]);

  const handleSearchModeChanged = useCallback((mode) => {
    setSearchMode(mode);
    setCurrentPage(1);
    setPhotos([]);
    setHasMore(false);
  }, []);

  return (
    <div className="App">
      <header className="App-header">
        <h1>Digital Collection Explorer</h1>
        <p>Explore historical photographs using natural language search</p>
      </header>
      
      <main className="App-main">
        <div className="search-controls">
          <SearchBar
            inputRef={searchInputRef}
            searchMode={searchMode}
            setSearchMode={handleSearchModeChanged}
            searchQuery={searchQuery}
            setSearchQuery={setSearchQuery}
            searchNearDate={searchNearDate}
            setSearchNearDate={setSearchNearDate}
            uploadedImage={uploadedImage}
            setUploadedImage={setUploadedImage}
            filepathSearchTerm={filepathSearchTerm}
            setFilepathSearchTerm={setFilepathSearchTerm}
            onSearchByText={handleSearchByText}
            onSearchByImage={handleSearchByImage}
            onSearchByDate={handleSearchByDate}
          />
        </div>
        <ResultsPerPageDropdown
          resultsPerPage={resultsPerPage}
          setResultsPerPage={setResultsPerPage}
          setCurrentPage={setCurrentPage}
          isLoading={isLoading}
        />
        <SearchResults
          photos={photos}
          isLoading={isLoading}
          error={error}
          currentPage={currentPage}
          setCurrentPage={setCurrentPage}
          hasMore={hasMore}
        />
        {
          photos.length === 0 && embeddingCount !== null && (
            <div className="welcome-message">
              <p>
                Enter a search term or upload a similar image to discover matches
                from our collection of {embeddingCount.toLocaleString()} photographs.
              </p>
            </div>
          )
        }
      </main>
    </div>
  );
}

export default App;
