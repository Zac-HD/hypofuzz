interface Option<T> {
  value: T;
  label: string;
}

interface Props<T> {
  value: T;
  onChange: (value: T) => void;
  options: Option<T>[];
}

export function Toggle<T>({ value, onChange, options }: Props<T>) {
  return (
    <div className="scale-toggle">
      {options.map(option => (
        <button
          key={String(option.value)}
          className={`scale-toggle__button ${value === option.value ? 'scale-toggle__button--active' : ''}`}
          onClick={() => onChange(option.value)}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}
