"use client";

import {
  useReactTable,
  getCoreRowModel,
  getSortedRowModel,
  getFilteredRowModel,
  flexRender,
  type ColumnDef,
  type SortingState,
  type RowData,
} from "@tanstack/react-table";
import { useState } from "react";
import { ChevronUp, ChevronDown, ChevronsUpDown } from "lucide-react";

// ─── Props ────────────────────────────────────────────────────────────────────

interface DataTableProps<TData extends RowData> {
  data: TData[];
  columns: ColumnDef<TData>[];
  globalFilter?: string;
  onRowClick?: (row: TData) => void;
  emptyText?: string;
}

// ─── Component ────────────────────────────────────────────────────────────────

export function DataTable<TData extends RowData>({
  data,
  columns,
  globalFilter = "",
  onRowClick,
  emptyText = "No data",
}: DataTableProps<TData>) {
  const [sorting, setSorting] = useState<SortingState>([]);

  const table = useReactTable({
    data,
    columns,
    state: { sorting, globalFilter },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
  });

  const thStyle: React.CSSProperties = {
    padding: "10px 12px",
    textAlign: "left",
    fontSize: "var(--text-xs)",
    fontWeight: 600,
    letterSpacing: "0.05em",
    textTransform: "uppercase",
    color: "var(--text-muted)",
    borderBottom: "1px solid var(--border)",
    userSelect: "none",
    whiteSpace: "nowrap",
  };

  const tdStyle: React.CSSProperties = {
    padding: "10px 12px",
    fontSize: "var(--text-sm)",
    color: "var(--text-primary)",
    borderBottom: "1px solid var(--border-muted)",
  };

  return (
    <div
      style={{
        overflowX: "auto",
        borderRadius: "var(--card-radius-sm)",
        border: "1px solid var(--border)",
      }}
    >
      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <thead>
          {table.getHeaderGroups().map((headerGroup) => (
            <tr key={headerGroup.id} style={{ background: "var(--bg-card)" }}>
              {headerGroup.headers.map((header) => (
                <th
                  key={header.id}
                  style={{
                    ...thStyle,
                    cursor: header.column.getCanSort() ? "pointer" : "default",
                  }}
                  onClick={header.column.getToggleSortingHandler()}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
                    {flexRender(header.column.columnDef.header, header.getContext())}
                    {header.column.getCanSort() && (
                      <span style={{ opacity: 0.5, display: "inline-flex" }}>
                        {header.column.getIsSorted() === "asc" ? (
                          <ChevronUp size={12} />
                        ) : header.column.getIsSorted() === "desc" ? (
                          <ChevronDown size={12} />
                        ) : (
                          <ChevronsUpDown size={12} />
                        )}
                      </span>
                    )}
                  </div>
                </th>
              ))}
            </tr>
          ))}
        </thead>
        <tbody>
          {table.getRowModel().rows.length === 0 ? (
            <tr>
              <td
                colSpan={columns.length}
                style={{
                  ...tdStyle,
                  textAlign: "center",
                  color: "var(--text-muted)",
                  padding: "32px",
                }}
              >
                {emptyText}
              </td>
            </tr>
          ) : (
            table.getRowModel().rows.map((row) => (
              <tr
                key={row.id}
                onClick={onRowClick ? () => onRowClick(row.original) : undefined}
                style={{
                  background: "var(--bg-card)",
                  cursor: onRowClick ? "pointer" : "default",
                  transition: "background var(--transition-fast)",
                }}
                onMouseEnter={(e) => {
                  if (onRowClick) {
                    (e.currentTarget as HTMLTableRowElement).style.background =
                      "var(--bg-card-hover)";
                  }
                }}
                onMouseLeave={(e) => {
                  (e.currentTarget as HTMLTableRowElement).style.background = "var(--bg-card)";
                }}
              >
                {row.getVisibleCells().map((cell) => (
                  <td key={cell.id} style={tdStyle}>
                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
                  </td>
                ))}
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}
