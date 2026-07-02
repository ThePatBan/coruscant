import { ProductPage } from "./ProductPage";

export function Personal() {
  return (
    <ProductPage productKey="personal">
      <div className="card">
        <span className="eyebrow">From discovery to monitoring</span>
        <p className="blurb">
          Save companies and searches to watchlists, add your holdings, and let Coruscant map exposure
          across geography, GICS sector, and MSCI market tier. A what-changed briefing surfaces material
          moves since you last looked, and alerts flag them as they land.
        </p>
        <p className="blurb">
          Exposure is <em>orientation</em>, not a dollar figure the data doesn't hold — proxy links are
          always labelled.
        </p>
      </div>
    </ProductPage>
  );
}
