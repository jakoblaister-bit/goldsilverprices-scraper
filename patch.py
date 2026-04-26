const fs = require('fs');
let c = fs.readFileSync('src/App.jsx', 'utf8');

// Replace entire BarsSection with proper cast/minted structure
const oldStart = c.indexOf('/* ── Bars section (homepage)');
const oldEnd   = c.indexOf('\n}', oldStart) + 2;

const newBars = `/* ── Bars section (homepage) ─────────────────────────────────────────────── */
function BarsSection({ rows }) {
  const [metal, setMetal]     = useState("gold");
  const [barType, setBarType] = useState("all");
  const navigate              = useNavigate();
  const mobile                = useIsMobile();

  // Filter rows
  const filtered = rows.filter(r =>
    r.category === "bar" &&
    r.metal === metal &&
    (barType === "all" || r.bar_type === barType) &&
    r.buy_price > 100
  );

  // Group by brand + size
  const grouped = {};
  for (const r of filtered) {
    const size  = r.weight_oz ? \`\${r.weight_oz}oz\` : \`\${r.weight_g}g\`;
    const brand = r.bar_brand || "Generic";
    const type  = r.bar_type  || "cast";
    const key   = \`\${brand}|\${type}|\${size}\`;
    if (!grouped[key]) grouped[key] = { brand, type, size, rows: [], weight_oz: r.weight_oz, weight_g: r.weight_g };
    grouped[key].rows.push(r);
  }

  // Sort by metal value (weight × spot approximation)
  const sortedGroups = Object.values(grouped).sort((a, b) => {
    const aOz = a.weight_oz || (a.weight_g / 31.1);
    const bOz = b.weight_oz || (b.weight_g / 31.1);
    return aOz - bOz;
  });

  const TAB_BTN = (label, val, current, setter) => (
    <button
      key={val}
      onClick={() => setter(val)}
      style={{
        background: current === val ? NAVY : "#fff",
        color: current === val ? "#fff" : SLATE,
        border: \`1px solid \${current === val ? NAVY : BORDER}\`,
        borderRadius: 5, padding: "4px 12px",
        fontSize: 11, fontWeight: current === val ? 600 : 400,
        cursor: "pointer", fontFamily: "inherit",
        whiteSpace: "nowrap",
      }}
    >{label}</button>
  );

  return (
    <div style={{
      background: "#fff", borderRadius: 10,
      border: \`1px solid \${BORDER}\`,
      boxShadow: "0 1px 3px rgba(0,0,0,.04)",
      overflow: "hidden",
    }}>
      {/* Header */}
      <div style={{
        padding: "10px 14px 0",
        display: "flex", alignItems: "center",
        justifyContent: "space-between",
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ fontSize: 16 }}>🏅</span>
          <span style={{ fontSize: 11, fontWeight: 700, color: SLATE, textTransform: "uppercase", letterSpacing: "0.06em" }}>
            Bars
          </span>
        </div>
        <span style={{ fontSize: 10, color: MUTED }}>{sortedGroups.length} types</span>
      </div>

      {/* Metal tabs */}
      <div style={{ display: "flex", gap: 5, padding: "8px 14px 6px", borderBottom: \`1px solid \${BORDER}\` }}>
        {[["Gold Bars","gold"],["Silver Bars","silver"]].map(([l,v]) => TAB_BTN(l, v, metal, (val) => { setMetal(val); setBarType("all"); }))}
        <div style={{ flex: 1 }} />
        {[["All","all"],["Cast","cast"],["Minted","minted"]].map(([l,v]) => TAB_BTN(l, v, barType, setBarType))}
      </div>

      {/* Column headers */}
      <div style={{
        display: "grid",
        gridTemplateColumns: "auto 1fr auto auto",
        padding: "5px 14px", gap: 8,
        background: NAVY,
        fontSize: 9, fontWeight: 700, color: "#64748B",
        textTransform: "uppercase", letterSpacing: "0.08em",
      }}>
        <span>Type</span>
        <span>Brand · Size</span>
        <span style={{ textAlign: "right" }}>From</span>
        <span />
      </div>

      {/* Rows */}
      {sortedGroups.length === 0
        ? <div style={{ padding: "20px 14px", textAlign: "center", color: MUTED, fontSize: 13 }}>No data</div>
        : sortedGroups.slice(0, 12).map((g, i) => {
            const cheapest = g.rows.sort((a,b) => a.buy_price - b.buy_price)[0];
            return (
              <div
                key={g.brand + g.type + g.size}
                onClick={() => navigate(\`/bars/\${metal}/\${g.type}/\${g.brand.toLowerCase().replace(/\s+/g,"-")}/\${g.size}\`)}
                style={{
                  display: "grid",
                  gridTemplateColumns: "auto 1fr auto auto",
                  alignItems: "center",
                  minHeight: 44,
                  padding: "0 14px", gap: 8,
                  background: i % 2 === 0 ? "#fff" : "#FAFBFC",
                  borderBottom: \`1px solid \${BORDER}\`,
                  cursor: "pointer",
                }}
              >
                {/* Cast/Minted badge */}
                <span style={{
                  fontSize: 8, fontWeight: 700,
                  background: g.type === "minted" ? "#EFF6FF" : "#F0FDF4",
                  color: g.type === "minted" ? "#1D4ED8" : "#16A34A",
                  padding: "2px 6px", borderRadius: 4,
                  textTransform: "uppercase", letterSpacing: "0.05em",
                  whiteSpace: "nowrap",
                }}>
                  {g.type}
                </span>

                {/* Brand + size */}
                <span style={{ fontSize: 12, color: "#1E293B" }}>
                  {g.brand} <span style={{ color: MUTED, fontSize: 11 }}>{g.size}</span>
                </span>

                {/* Price */}
                <span style={{ fontSize: 13, fontWeight: 600, color: NAVY, whiteSpace: "nowrap", fontFamily: "'Inter',system-ui,sans-serif" }}>
                  {fmt(cheapest.buy_price)}
                </span>

                {/* Arrow */}
                <span style={{ fontSize: 12, color: MUTED }}>›</span>
              </div>
            );
          })
      }

      {/* All bars link */}
      {sortedGroups.length > 12 && (
        <div style={{ padding: "8px 14px", textAlign: "right", borderTop: \`1px solid \${BORDER}\` }}>
          <span style={{ fontSize: 11, color: NAVY, cursor: "pointer", fontWeight: 500 }}>
            All {metal} bars ›
          </span>
        </div>
      )}
    </div>
  );
}
`;

c = c.slice(0, oldStart) + newBars + c.slice(oldEnd);

fs.writeFileSync('src/App.jsx', c, 'utf8');
console.log('✓ BarsSection redesigned');
console.log('Cast/Minted tabs:', c.includes('Cast","cast"'));