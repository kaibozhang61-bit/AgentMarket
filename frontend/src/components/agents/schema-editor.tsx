"use client";

import { Plus, Trash2 } from "lucide-react";
import type { FieldSchema } from "@/lib/types";

interface Props {
  title: string;
  fields: FieldSchema[];
  onChange: (fields: FieldSchema[]) => void;
}

const TYPES = ["string", "number", "boolean", "list<string>", "object"];

function empty(): FieldSchema {
  return { fieldName: "", type: "string", required: true, description: "" };
}

export function SchemaEditor({ title, fields, onChange }: Props) {
  function update(i: number, key: keyof FieldSchema, val: unknown) {
    const next = fields.map((f, j) => (j === i ? { ...f, [key]: val } : f));
    onChange(next);
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium text-neutral-700">{title}</h3>
        <button
          type="button"
          onClick={() => onChange([...fields, empty()])}
          className="flex items-center gap-1 text-xs text-neutral-500 hover:text-neutral-900"
        >
          <Plus className="h-3.5 w-3.5" />
          Add field
        </button>
      </div>

      {fields.length === 0 && (
        <p className="text-xs text-neutral-400">No fields defined.</p>
      )}

      {fields.map((f, i) => (
        <div key={i} className="flex items-start gap-2">
          <input
            placeholder="fieldName"
            value={f.fieldName}
            onChange={(e) => update(i, "fieldName", e.target.value)}
            className="w-36 rounded border px-2 py-1.5 text-xs outline-none focus:ring-1 focus:ring-neutral-900"
          />
          <select
            value={f.type}
            onChange={(e) => update(i, "type", e.target.value)}
            className="w-28 rounded border px-2 py-1.5 text-xs outline-none focus:ring-1 focus:ring-neutral-900"
          >
            {TYPES.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
          <input
            placeholder="description"
            value={f.description ?? ""}
            onChange={(e) => update(i, "description", e.target.value)}
            className="flex-1 rounded border px-2 py-1.5 text-xs outline-none focus:ring-1 focus:ring-neutral-900"
          />
          <label className="flex items-center gap-1 pt-1.5 text-xs text-neutral-500">
            <input
              type="checkbox"
              checked={f.required}
              onChange={(e) => update(i, "required", e.target.checked)}
              className="h-3 w-3"
            />
            req
          </label>
          <button
            type="button"
            onClick={() => onChange(fields.filter((_, j) => j !== i))}
            className="pt-1.5 text-neutral-300 hover:text-red-500"
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        </div>
      ))}
    </div>
  );
}
