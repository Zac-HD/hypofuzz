import { faArrowLeftLong, faArrowRightLong } from "@fortawesome/free-solid-svg-icons"
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome"

interface PaginationProps {
  currentPage: number
  pageCount: number
  onPageChange: (page: number) => void
}

export function Pagination({ currentPage, pageCount, onPageChange }: PaginationProps) {
  console.assert(pageCount > 1)

  function getPageNumbers(): (number | "ellipsis")[] {
    if (pageCount <= 7) {
      return Array.from({ length: pageCount }, (_, i) => i)
    }

    if (currentPage <= 3) {
      return [0, 1, 2, 3, 4, "ellipsis", pageCount - 1]
    }

    if (currentPage >= pageCount - 4) {
      return [
        0,
        "ellipsis",
        pageCount - 5,
        pageCount - 4,
        pageCount - 3,
        pageCount - 2,
        pageCount - 1,
      ]
    }

    return [
      0,
      "ellipsis",
      currentPage - 1,
      currentPage,
      currentPage + 1,
      "ellipsis",
      pageCount - 1,
    ]
  }

  const pageNumbers = getPageNumbers()

  function handlePageClick(page: number | string) {
    if (typeof page === "number" && currentPage !== page) {
      onPageChange(page)
    }
  }

  function handlePrevious() {
    if (currentPage > 0) {
      onPageChange(currentPage - 1)
    }
  }

  function handleNext() {
    if (currentPage < pageCount - 1) {
      onPageChange(currentPage + 1)
    }
  }

  return (
    <div className="pagination">
      <div
        className={`pagination__nav pagination__nav--left ${
          currentPage === 0 ? "pagination__nav--disabled" : ""
        }`}
        onClick={handlePrevious}
      >
        <FontAwesomeIcon icon={faArrowLeftLong} />
      </div>

      {pageNumbers.map((page, index) => {
        if (page === "ellipsis") {
          return (
            <div key={`ellipsis-${index}`} className=" pagination__ellipsis">
              ...
            </div>
          )
        }

        const isCurrentPage = page === currentPage

        return (
          <div
            key={page}
            className={`pagination__number ${
              isCurrentPage ? "pagination__number--current" : ""
            }`}
            onClick={() => handlePageClick(page)}
          >
            {page + 1}
          </div>
        )
      })}

      <div
        className={`pagination__nav pagination__nav--right ${
          currentPage === pageCount - 1 ? "pagination__nav--disabled" : ""
        }`}
        onClick={handleNext}
      >
        <FontAwesomeIcon icon={faArrowRightLong} />
      </div>
    </div>
  )
}
