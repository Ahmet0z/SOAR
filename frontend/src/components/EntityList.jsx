import PropTypes from 'prop-types'

function EntityList({
  items,
  selectedId,
  onSelect,
  getPrimary,
  getSecondary,
  emptyLabel = 'Kayıt bulunamadı'
}) {
  if (!items.length) {
    return <p className="empty-state">{emptyLabel}</p>
  }

  return (
    <ul className="entity-list">
      {items.map((item) => (
        <li key={item.id}>
          <button
            type="button"
            className={selectedId === item.id ? 'entity active' : 'entity'}
            onClick={() => onSelect(item.id)}
          >
            <span className="primary">{getPrimary(item)}</span>
            {getSecondary && <span className="secondary">{getSecondary(item)}</span>}
          </button>
        </li>
      ))}
    </ul>
  )
}

EntityList.propTypes = {
  items: PropTypes.array.isRequired,
  selectedId: PropTypes.string,
  onSelect: PropTypes.func.isRequired,
  getPrimary: PropTypes.func.isRequired,
  getSecondary: PropTypes.func,
  emptyLabel: PropTypes.string
}

export default EntityList
