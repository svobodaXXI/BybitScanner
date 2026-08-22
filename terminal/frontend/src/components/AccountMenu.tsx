export function AccountMenu() {
  return (
    <section className="account-menu" aria-label="Account selection">
      <div>
        <strong>Paper / Virtual</strong>
        <small>Selected · safe local prototype</small>
      </div>
      <button disabled type="button">
        Real credentials unavailable
      </button>
    </section>
  );
}
