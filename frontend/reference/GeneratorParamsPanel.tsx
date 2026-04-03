/**
 * Referencia React + Tailwind (copiar a un proyecto Vite/React).
 * El producto empaquetado usa generator_params_panel.js + index.html.
 */
import { useMemo, useState, useCallback } from "react";

type DayKey = "Vie" | "Sáb" | "Dom" | "Lun" | "Mar" | "Mié" | "Jue";

type Flags = {
  forced_libres: boolean;
  forced_quebrado: boolean;
  allow_no_rest: boolean;
  strict_preferences: boolean;
  is_jefe_pista: boolean;
};

export type GeneratorRow = {
  employee_id: number;
  nombre: string;
  flags: Flags;
  pref_plantilla_id: number | null;
  preference_source?: string;
  shift_preferences: Partial<Record<DayKey, string>>;
  absences: { type: string; date?: string; note?: string }[];
};

type Props = {
  initialRows: GeneratorRow[];
  onSave: (rows: GeneratorRow[]) => Promise<void>;
};

const DAYS: DayKey[] = ["Vie", "Sáb", "Dom", "Lun", "Mar", "Mié", "Jue"];

function summarizeShifts(p: Partial<Record<DayKey, string>>): string {
  const entries = DAYS.map((d) => [d, p[d]] as const).filter(([, v]) => v && v !== "AUTO");
  if (entries.length === 0) return "—";
  return entries.slice(0, 3).map(([d, c]) => `${d}:${c}`).join(" · ") + (entries.length > 3 ? "…" : "");
}

export function GeneratorParamsPanel({ initialRows, onSave }: Props) {
  const [rows, setRows] = useState<GeneratorRow[]>(() => initialRows.slice());
  const [selected, setSelected] = useState<Set<number>>(() => new Set());
  const [activeId, setActiveId] = useState<number | null>(null);

  const active = useMemo(() => rows.find((r) => r.employee_id === activeId) ?? null, [rows, activeId]);

  const patchRow = useCallback((id: number, fn: (r: GeneratorRow) => GeneratorRow) => {
    setRows((prev) => prev.map((r) => (r.employee_id === id ? fn(r) : r)));
  }, []);

  const toggleFlag = (id: number, key: keyof Flags, value: boolean) => {
    patchRow(id, (r) => ({
      ...r,
      flags: { ...r.flags, [key]: value },
    }));
  };

  const applyBatch = (key: keyof Flags, value: boolean) => {
    setRows((prev) =>
      prev.map((r) => {
        if (selected.size && !selected.has(r.employee_id)) return r;
        if (r.pref_plantilla_id && key !== "is_jefe_pista") return r;
        return { ...r, flags: { ...r.flags, [key]: value } };
      }),
    );
  };

  const flagKeys: (keyof Flags)[] = [
    "forced_libres",
    "forced_quebrado",
    "allow_no_rest",
    "strict_preferences",
    "is_jefe_pista",
  ];

  return (
    <div className="flex min-h-[480px] flex-col gap-3 bg-slate-50 p-4 text-slate-900">
      <header className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-200 pb-3">
        <div>
          <h1 className="text-lg font-semibold tracking-tight">Parámetros del generador</h1>
          <p className="text-xs text-slate-500">Matriz por colaborador · detalle lateral</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            className="rounded border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium hover:bg-slate-100"
            onClick={() => applyBatch("forced_quebrado", true)}
          >
            Lote: Forzar quebrado ON
          </button>
          <button
            type="button"
            className="rounded bg-slate-900 px-3 py-1.5 text-xs font-medium text-white hover:bg-slate-800"
            onClick={() => onSave(rows)}
          >
            Guardar todo
          </button>
        </div>
      </header>

      <div className="grid flex-1 grid-cols-1 gap-3 lg:grid-cols-[1fr_320px]">
        <div className="overflow-auto rounded border border-slate-200 bg-white shadow-sm">
          <table className="min-w-full border-collapse text-left text-xs">
            <thead className="sticky top-0 z-10 bg-slate-100 text-[11px] uppercase text-slate-600">
              <tr>
                <th className="border-b border-slate-200 px-2 py-2">
                  <input
                    type="checkbox"
                    aria-label="Seleccionar todos"
                    onChange={(e) =>
                      setSelected(e.target.checked ? new Set(rows.map((r) => r.employee_id)) : new Set())
                    }
                  />
                </th>
                <th className="border-b border-slate-200 px-2 py-2">Colaborador</th>
                <th className="border-b border-slate-200 px-2 py-2 text-center">Libres</th>
                <th className="border-b border-slate-200 px-2 py-2 text-center">Quebrado</th>
                <th className="border-b border-slate-200 px-2 py-2 text-center">Sin desc.</th>
                <th className="border-b border-slate-200 px-2 py-2 text-center">Estricto</th>
                <th className="border-b border-slate-200 px-2 py-2 text-center">Jefe</th>
                <th className="border-b border-slate-200 px-2 py-2">Turnos</th>
                <th className="border-b border-slate-200 px-2 py-2">Aus.</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr
                  key={r.employee_id}
                  className={r.employee_id === activeId ? "bg-sky-50" : "even:bg-slate-50/60"}
                >
                  <td className="border-b border-slate-100 px-2 py-1.5">
                    <input
                      type="checkbox"
                      checked={selected.has(r.employee_id)}
                      onChange={(e) => {
                        const n = new Set(selected);
                        e.target.checked ? n.add(r.employee_id) : n.delete(r.employee_id);
                        setSelected(n);
                      }}
                      aria-label={`Seleccionar ${r.nombre}`}
                    />
                  </td>
                  <td className="border-b border-slate-100 px-2 py-1.5 font-medium">
                    <button
                      type="button"
                      className="text-left hover:underline"
                      onClick={() => setActiveId(r.employee_id)}
                    >
                      {r.nombre}
                    </button>
                  </td>
                  {flagKeys.map((k) => {
                    const dis = !!(r.pref_plantilla_id && k !== "is_jefe_pista");
                    return (
                      <td key={k} className="border-b border-slate-100 px-1 py-1 text-center">
                        <button
                          type="button"
                          role="switch"
                          aria-checked={r.flags[k]}
                          disabled={dis}
                          className={`inline-flex h-5 w-9 rounded-full border transition ${
                            r.flags[k] ? "border-sky-600 bg-sky-600" : "border-slate-300 bg-slate-200"
                          } ${dis ? "opacity-40" : ""}`}
                          onClick={() => !dis && toggleFlag(r.employee_id, k, !r.flags[k])}
                        >
                          <span
                            className={`m-0.5 h-4 w-4 rounded-full bg-white shadow transition ${
                              r.flags[k] ? "translate-x-4" : ""
                            }`}
                          />
                        </button>
                      </td>
                    );
                  })}
                  <td className="border-b border-slate-100 px-2 py-1 text-slate-600">
                    {summarizeShifts(r.shift_preferences)}
                  </td>
                  <td className="border-b border-slate-100 px-2 py-1">
                    <button
                      type="button"
                      className="rounded border border-slate-200 px-2 py-0.5 text-[11px] hover:bg-slate-100"
                      onClick={() => setActiveId(r.employee_id)}
                    >
                      {r.absences.length ? `${r.absences.length}` : "—"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <aside className="flex flex-col rounded border border-slate-200 bg-white p-3 text-sm shadow-sm">
          <h2 className="border-b border-slate-100 pb-2 text-xs font-semibold uppercase text-slate-500">Detalle</h2>
          {!active ? (
            <p className="mt-3 text-xs text-slate-500">Seleccioná un colaborador.</p>
          ) : (
            <div className="mt-3 flex flex-col gap-3">
              <p className="font-medium">{active.nombre}</p>
              {active.pref_plantilla_id != null && (
                <p className="text-xs text-amber-700">Plantilla #{active.pref_plantilla_id}</p>
              )}
              <ul className="max-h-40 list-disc pl-4 text-xs text-slate-700">
                {active.absences.length === 0 && <li>Sin ausencias en vista</li>}
                {active.absences.map((a, i) => (
                  <li key={i}>
                    {a.type} {a.date}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </aside>
      </div>
    </div>
  );
}
