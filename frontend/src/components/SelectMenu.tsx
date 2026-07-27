import { materialValue, MdOutlinedSelect, MdSelectOption } from "./MaterialControls";

export interface SelectMenuOption {
  value: string;
  label: string;
}

export function SelectMenu({
  label,
  value,
  options,
  onChange,
  className = "",
  disabled = false,
}: {
  label: string;
  heading?: string;
  value: string;
  options: SelectMenuOption[];
  onChange: (value: string) => void;
  className?: string;
  align?: "left" | "right";
  disabled?: boolean;
}) {
  return (
    <MdOutlinedSelect
      className={`m3-select ${className}`}
      label={label}
      value={value}
      disabled={disabled}
      onChange={(event) => onChange(materialValue(event))}
    >
      {options.map((option) => (
        <MdSelectOption
          key={option.value}
          value={option.value}
          selected={option.value === value}
        >
          <div slot="headline">{option.label}</div>
        </MdSelectOption>
      ))}
    </MdOutlinedSelect>
  );
}
