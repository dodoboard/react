import type { Attribute, Level, Selection } from "../types";
import { Chip, Segmented } from "./ui";

const LEVEL_LABELS: Record<Level, string> = { average: "Average", notable: "Notable", extreme: "Extreme" };

export function AttributeField(props: {
  attribute: Attribute;
  levels: Level[];
  selection: Selection | undefined;
  onChange: (next: Selection | undefined) => void;
}) {
  const { attribute: a, selection } = props;
  const values = selection?.values ?? [];
  const level = selection?.level ?? "average";
  const full = values.length >= a.max_select;

  const toggle = (id: string) => {
    let next: string[];
    if (values.includes(id)) next = values.filter((v) => v !== id);
    else if (a.max_select === 1) next = [id];
    else if (full) return;
    else next = [...values, id];
    props.onChange(next.length ? { values: next, level } : undefined);
  };

  return (
    <fieldset className="field">
      <legend className="field__label">
        {a.label}
        {a.max_select > 1 && (
          <span className="muted">
            {" "}
            {values.length}/{a.max_select}
          </span>
        )}
      </legend>
      <div className="chips">
        {a.options.map((o) => (
          <Chip key={o.id} active={values.includes(o.id)} disabled={a.max_select > 1 && full} onClick={() => toggle(o.id)}>
            {o.label}
          </Chip>
        ))}
      </div>
      {a.leveled && values.length > 0 && (
        <Segmented
          size="sm"
          label={`${a.label} intensity`}
          value={level}
          options={props.levels.map((l) => ({ value: l, label: LEVEL_LABELS[l] }))}
          onChange={(l) => props.onChange({ values, level: l })}
        />
      )}
    </fieldset>
  );
}
