# Frontend Integration Guide: Metadata Filtering for RAG Chat

## Overview
The backend now supports metadata filtering for paper retrieval. This guide explains how to integrate these filters into the frontend chat interface.

## Available Filter Parameters

All filters are passed via `meta_params` in the chat request:

```typescript
interface ChatMetaParams {
  // Existing params
  mode?: "basic" | "deep";           // Chat mode
  stream?: boolean;                  // Enable streaming (default: true)
  language?: string;                 // e.g., "id-ID", "en-US"
  timezone?: string;                 // e.g., "Asia/Jakarta"
  source_preference?: "all" | "only_papers" | "only_general";
  conversation_id?: string;          // For continuing conversations
  is_incognito?: boolean;            // Don't save to history
  
  // NEW: Filter params
  catalog_type?: string;             // Filter by document type
  year_from?: number;                // Minimum publication year
  year_to?: number;                  // Maximum publication year
  author?: string;                   // Filter by author name
  has_electronic_access?: boolean;   // Only papers with online access
}
```

## Filter Details

### 1. Catalog Type (`catalog_type`)
Filter by document type. Available values:

| User-Friendly Name | API Value |
|-------------------|-----------|
| Thesis / S2 / Master | `"Karya Ilmiah - Thesis (S2) - Reference"` |
| Skripsi / S1 / Bachelor | `"Karya Ilmiah - Skripsi (S1) - Reference"` |
| Disertasi / S3 / PhD | `"Karya Ilmiah - Disertasi (S3) - Reference"` |
| Jurnal Internasional | `"Jurnal Internasional - Reference"` |
| Jurnal Nasional | `"Jurnal Nasional - Reference"` |
| Jurnal Terakreditasi | `"Jurnal Terakreditasi DIKTI - Reference"` |
| E-Book / Ebook | `"Buku - Elektronik (E-Book)"` |
| Proceeding / Konferensi | `"Proceeding (Electronic)"` |
| Artikel | `"Artikel - Restricted Use"` |
| E-Article | `"E-Article"` |
| Case Study | `"Case Studies"` |
| Modul Praktikum | `"Modul Praktikum ( Electronic )"` |
| ePoster | `"ePoster"` |

**Note:** The backend has alias mapping, so you can also pass user-friendly names like `"thesis"`, `"skripsi"`, `"jurnal internasional"` and they will be normalized automatically.

### 2. Year Range (`year_from`, `year_to`)
Filter by publication year range:
- `year_from`: Minimum year (e.g., `2020`)
- `year_to`: Maximum year (e.g., `2024`)
- Can use individually or together
- Example: Recent 5 years → `year_from: 2020`, `year_to: 2025`

### 3. Author (`author`)
Filter by author name:
- Partial match supported
- Case-insensitive
- Example: `"Prof. Ahmad"`, `"Siti Nurhaliza"`

### 4. Electronic Access (`has_electronic_access`)
Filter for papers with online/electronic access:
- `true`: Only papers with `access_link` (downloadable/online)
- `undefined/null`: Include all papers

## API Request Examples

### Basic Chat with Filters
```typescript
const response = await fetch('/chat/basic', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    query: "What are the latest developments in AI?",
    meta_params: {
      catalog_type: "Jurnal Internasional - Reference",
      year_from: 2023,
      has_electronic_access: true,
      language: "id-ID"
    }
  })
});
```

### Streaming Chat with Filters
```typescript
const response = await fetch('/chat/new', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    query: "Find thesis about machine learning",
    meta_params: {
      catalog_type: "Karya Ilmiah - Thesis (S2) - Reference",
      year_from: 2020,
      year_to: 2024,
      stream: true
    }
  })
});

// Handle SSE stream
const reader = response.body?.getReader();
// ... stream processing
```

### Natural Language with Auto-Extracted Filters
If you don't specify filters explicitly, the backend can extract them from natural language:

```typescript
// User asks: "Find recent papers by Prof. Ahmad about deep learning"
// Backend will auto-extract: author="Prof. Ahmad", year_from=2020 (recent)

const response = await fetch('/chat/new', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    query: "Find recent papers by Prof. Ahmad about deep learning",
    meta_params: {
      stream: true,
      language: "en-US"
      // Filters will be auto-extracted from query
    }
  })
});
```

## UI Component Suggestions

### 1. Filter Panel/Drawer
```typescript
// Suggested component structure
<FilterPanel>
  <CatalogTypeSelect 
    value={catalogType}
    onChange={setCatalogType}
    options={[
      { label: "All Types", value: undefined },
      { label: "Thesis (S2)", value: "Karya Ilmiah - Thesis (S2) - Reference" },
      { label: "Skripsi (S1)", value: "Karya Ilmiah - Skripsi (S1) - Reference" },
      { label: "Jurnal Internasional", value: "Jurnal Internasional - Reference" },
      { label: "E-Book", value: "Buku - Elektronik (E-Book)" },
      // ... more options
    ]}
  />
  
  <YearRangePicker
    from={yearFrom}
    to={yearTo}
    onFromChange={setYearFrom}
    onToChange={setYearTo}
    presets={[
      { label: "Last 5 Years", from: 2020, to: 2025 },
      { label: "Last 10 Years", from: 2015, to: 2025 },
      { label: "2020-2024", from: 2020, to: 2024 },
    ]}
  />
  
  <AuthorInput
    value={author}
    onChange={setAuthor}
    placeholder="Filter by author name..."
  />
  
  <Checkbox
    checked={hasElectronicAccess}
    onChange={setHasElectronicAccess}
    label="Only show papers with online access"
  />
  
  <Button onClick={applyFilters}>Apply Filters</Button>
  <Button onClick={clearFilters} variant="secondary">Clear</Button>
</FilterPanel>
```

### 2. Quick Filter Chips
```typescript
// Quick filter buttons for common filters
<QuickFilters>
  <FilterChip 
    label="Thesis Only"
    onClick={() => setCatalogType("Karya Ilmiah - Thesis (S2) - Reference")}
  />
  <FilterChip 
    label="Recent (5 Years)"
    onClick={() => { setYearFrom(2020); setYearTo(2025); }}
  />
  <FilterChip 
    label="Online Access"
    onClick={() => setHasElectronicAccess(true)}
  />
  <FilterChip 
    label="Jurnal Internasional"
    onClick={() => setCatalogType("Jurnal Internasional - Reference")}
  />
</QuickFilters>
```

### 3. Filter Tags/Badges
Show active filters as removable tags:
```typescript
<ActiveFilters>
  {catalogType && (
    <FilterTag 
      label={`Type: ${formatCatalogType(catalogType)}`}
      onRemove={() => setCatalogType(undefined)}
    />
  )}
  {yearFrom && yearTo && (
    <FilterTag 
      label={`Years: ${yearFrom}-${yearTo}`}
      onRemove={() => { setYearFrom(undefined); setYearTo(undefined); }}
    />
  )}
  {author && (
    <FilterTag 
      label={`Author: ${author}`}
      onRemove={() => setAuthor(undefined)}
    />
  )}
  {hasElectronicAccess && (
    <FilterTag 
      label="Online Access Only"
      onRemove={() => setHasElectronicAccess(undefined)}
    />
  )}
</ActiveFilters>
```

## Integration Flow

### 1. Store Filters in State
```typescript
const [filters, setFilters] = useState({
  catalog_type: undefined as string | undefined,
  year_from: undefined as number | undefined,
  year_to: undefined as number | undefined,
  author: undefined as string | undefined,
  has_electronic_access: undefined as boolean | undefined,
});
```

### 2. Pass Filters to Chat API
```typescript
const sendMessage = async (query: string) => {
  const response = await fetch('/chat/new', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      query,
      meta_params: {
        stream: true,
        language: "id-ID",
        ...filters, // Spread filter values
      }
    })
  });
  
  // Handle streaming response...
};
```

### 3. Auto-Extract Filters from Query (Optional)
You can also send queries without explicit filters and let the backend extract them:

```typescript
// Frontend doesn't set filters
// User types: "Find thesis about AI from 2023 by John Doe"
// Backend extracts: catalog_type="thesis", year_from=2023, author="John Doe"
```

## Important Notes

1. **Filter Persistence**: Filters should persist across messages in the same conversation (store in component state or context)

2. **Clear Filters**: Provide a way to clear/reset filters easily

3. **Validation**: 
   - `year_from` should be ≤ `year_to`
   - Years should be reasonable (e.g., 1900-2030)

4. **Performance**: Filters are applied at the database level (pgvector), so they're very efficient

5. **Backward Compatibility**: If no filters are provided, the system works exactly as before (no breaking changes)

6. **Filter Combinations**: All filters work together with AND logic:
   - `(catalog_type = "Thesis") AND (year >= 2020) AND (year <= 2024) AND (author ILIKE "%Ahmad%")`

## Error Handling

Filters are validated by Pydantic models. Invalid values will return 422 errors:

```typescript
// Example error response
{
  "detail": [
    {
      "loc": ["body", "meta_params", "year_from"],
      "msg": "ensure this value is greater than or equal to 1900",
      "type": "value_error.number.not_ge"
    }
  ]
}
```

## Testing Examples

Test these scenarios:

1. **Type Filter**: "Find skripsi about machine learning" → Should only return S1 papers
2. **Year Filter**: "Show papers from 2020-2024" → Should only return papers in that range
3. **Author Filter**: "Papers by Prof. Ahmad about AI" → Should filter by author
4. **Combined**: "Thesis from 2022 by Siti about deep learning" → Multiple filters
5. **Electronic Only**: "Downloadable papers about IoT" → Only papers with access_link

## Endpoint Support

Filters work on both endpoints:
- `POST /chat/basic` - Original RAG service
- `POST /chat/new` - LangGraph-powered RAG (recommended)

Both endpoints accept the same `meta_params` structure.
