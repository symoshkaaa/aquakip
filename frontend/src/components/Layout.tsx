import { useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import {
  ArrowUpRight,
  Boxes,
  ClipboardList,
  FileText,
  GitCompareArrows,
  LayoutDashboard,
  Menu,
  PackageCheck,
  Shuffle,
  Send,
  Truck,
  X,
} from "lucide-react";

const navigation = [
  { to: "/dashboard", label: "Обзор", icon: LayoutDashboard },
  { to: "/suppliers", label: "Поставщики", icon: Boxes },
  { to: "/purchase-requests", label: "Заявки на закупку", icon: ClipboardList },
  { to: "/rfqs", label: "RFQ", icon: Send },
  { to: "/supplier-offers", label: "Предложения", icon: FileText },
  { to: "/supplier-comparisons", label: "Сравнения", icon: GitCompareArrows },
  { to: "/purchase-orders", label: "Заказы поставщикам", icon: PackageCheck },
  { to: "/alternative-requests", label: "Запросы на аналоги", icon: Shuffle },
  { to: "/expected-deliveries", label: "Ожидаемые поставки", icon: Truck },
];

export default function Layout() {
  const location = useLocation();
  const [menuOpen, setMenuOpen] = useState(false);
  const detailTitles = [
    ["/rfqs/", "Детали RFQ"],
    ["/purchase-orders/", "Детали заказа"],
    ["/supplier-comparisons/", "Детали сравнения"],
    ["/suppliers/", "Поставщик"],
    ["/purchase-requests/", "Заявка на закупку"],
    ["/supplier-offers/", "Предложение поставщика"],
  ] as const;
  const title = detailTitles.find(([prefix]) => location.pathname.startsWith(prefix))?.[1]
    ?? navigation.find((item) => location.pathname === item.to)?.label
    ?? "Обзор";

  return (
    <div className="app-shell">
      {menuOpen && (
        <button
          aria-label="Закрыть меню"
          className="sidebar-scrim"
          onClick={() => setMenuOpen(false)}
          type="button"
        />
      )}
      <aside className={`sidebar ${menuOpen ? "sidebar--open" : ""}`}>
        <div className="brand">
          <div className="brand__mark">AK</div>
          <div>
            <strong>Aqua Kip</strong>
            <span>PROCUREMENT</span>
          </div>
          <button
            aria-label="Закрыть навигацию"
            className="sidebar__close"
            onClick={() => setMenuOpen(false)}
            type="button"
          >
            <X size={19} />
          </button>
        </div>

        <div className="sidebar__label">РАБОЧЕЕ ПРОСТРАНСТВО</div>
        <nav aria-label="Основная навигация" className="navigation">
          {navigation.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              className={({ isActive }) => `navigation__link ${isActive ? "navigation__link--active" : ""}`}
              onClick={() => setMenuOpen(false)}
              to={to}
            >
              <Icon size={18} strokeWidth={1.8} />
              <span>{label}</span>
              {to === "/rfqs" && <ArrowUpRight className="navigation__hint" size={14} />}
            </NavLink>
          ))}
        </nav>

        <div className="sidebar__bottom">
          <span className="sidebar__bottom-mark">A</span>
          <div>
            <strong>Aqua Kip Platform</strong>
            <span>Procurement service</span>
          </div>
        </div>
      </aside>

      <div className="workspace">
        <header className="topbar">
          <button
            aria-label="Открыть навигацию"
            className="icon-button topbar__menu"
            onClick={() => setMenuOpen(true)}
            type="button"
          >
            <Menu size={20} />
          </button>
          <div className="topbar__crumb">
            <span>Закупки</span>
            <span className="topbar__slash">/</span>
            <strong>{title}</strong>
          </div>
          <div className="topbar__service">Aqua Kip</div>
        </header>
        <main className="main-content">
          <Outlet />
        </main>
        <footer className="footer">
          <span>Aqua Kip</span>
          <span>Закупки</span>
        </footer>
      </div>
    </div>
  );
}
