interface TableProps<T> {
  headers: string[]
  data: T[]
  row: (item: T) => React.ReactNode[]
  getKey: (item: T) => string | number
}

export function Table<T>({ headers, data, row, getKey }: TableProps<T>) {
  return (
    <table className="table">
      <thead>
        <tr>
          {headers.map((header, index) => (
            <th key={index}>{header}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {data.map(item => {
          const rowValue = row(item)
          console.assert(rowValue.length === headers.length)
          return (
            <tr key={getKey(item)}>
              {rowValue.map((cell, colIndex) => (
                <td key={colIndex}>{cell}</td>
              ))}
            </tr>
          )
        })}
      </tbody>
    </table>
  )
}
