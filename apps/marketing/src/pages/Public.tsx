import { ProductPage } from "./ProductPage";
import { COVERAGE_NOTE } from "../content";

export function Public() {
  return (
    <ProductPage productKey="public">
      <div className="card">
        <span className="eyebrow">What you can do</span>
        <p className="blurb">
          Search any covered company, open its profile, and walk the relationship graph — officers,
          subsidiaries, sector and market-tier classifications, and co-mentions. Open each edge to the
          filing or public classification behind it.
        </p>
        <p className="blurb">{COVERAGE_NOTE}</p>
        <span className="pill">Free · no account needed</span>
      </div>
    </ProductPage>
  );
}
