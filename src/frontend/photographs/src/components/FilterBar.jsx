import './FilterBar.css';

function FilterBar({
  filepathSearchTerm,
  setFilepathSearchTerm,
}) {
    return (
    <div className="filter-bar">
          <>
          <div className='sub-text'>Limit to file paths containing: </div>
            <input
              type="text"
              placeholder="Text in file path..."
              className="search-input"
              aria-label="Search photographs"
              value={filepathSearchTerm}
              onChange={(e) => setFilepathSearchTerm(e.target.value)}
            />
          </>
    </div>
    )
}

export default FilterBar;