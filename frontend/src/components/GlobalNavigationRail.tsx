import { useState, type CSSProperties, type ReactNode } from "react";
import addIcon from "@material-symbols/svg-400/rounded/add.svg?url";
import companiesIcon from "@material-symbols/svg-400/rounded/domain.svg?url";
import collectionsIcon from "@material-symbols/svg-400/rounded/folder.svg?url";
import collapseIcon from "@material-symbols/svg-400/rounded/menu_open.svg?url";
import expandIcon from "@material-symbols/svg-400/rounded/menu.svg?url";
import moreIcon from "@material-symbols/svg-400/rounded/arrow_drop_down.svg?url";
import settingsIcon from "@material-symbols/svg-400/rounded/settings.svg?url";
import scheduledIcon from "@material-symbols/svg-400/rounded/schedule.svg?url";

import { ImportCsvModal } from "./modals/ImportCsvModal";

type Workspace = "companies" | "collections" | "scheduled" | "about";

interface Props {
  workspace: Workspace;
  onWorkspaceChange: (workspace: Workspace) => void;
  onAddCompany: () => void;
}

function MaterialIcon({ src }: { src: string }) {
  return (
    <span
      className="m3-material-symbol"
      style={{ "--m3-symbol-url": `url("${src}")` } as CSSProperties}
      aria-hidden="true"
    />
  );
}

function RailItem({ active, label, icon, expanded, onClick }: { active: boolean; label: string; icon: ReactNode; expanded: boolean; onClick: () => void }) {
  return (
    <button type="button" className={`m3-rail-item ${active ? "m3-rail-item-selected" : ""}`} aria-current={active ? "page" : undefined} aria-label={label} title={label} onClick={onClick}>
      <span className="m3-rail-icon">{icon}</span>
      <span className={expanded ? "" : "sr-only"}>{label}</span>
    </button>
  );
}

const icons = { expand: <MaterialIcon src={expandIcon} />, collapse: <MaterialIcon src={collapseIcon} />, add: <MaterialIcon src={addIcon} />, companies: <MaterialIcon src={companiesIcon} />, collections: <MaterialIcon src={collectionsIcon} />, scheduled: <MaterialIcon src={scheduledIcon} />, settings: <MaterialIcon src={settingsIcon} /> };

export function GlobalNavigationRail({ workspace, onWorkspaceChange, onAddCompany }: Props) {
  const [expanded, setExpanded] = useState(() => typeof window === "undefined" || window.innerWidth >= 1024);
  const [showImport, setShowImport] = useState(false);
  const [showCreateMenu, setShowCreateMenu] = useState(false);
  return (
    <>
      <nav aria-label="Primary navigation" className={`global-navigation-rail ${expanded ? "global-navigation-rail-expanded" : "global-navigation-rail-collapsed"} hidden shrink-0 flex-col sm:flex`}>
        <div className="m3-rail-brand">
          <span className="m3-rail-brand-mark" aria-hidden="true">
            <svg viewBox="0 0 32 32" fill="none"><circle cx="7" cy="16" r="3" fill="currentColor" /><circle cx="24" cy="8" r="3" fill="currentColor" /><circle cx="24" cy="24" r="3" fill="currentColor" /><path d="m10 15 11-5M10 17l11 5" stroke="currentColor" strokeWidth="1.5" /></svg>
          </span>
          <span className={expanded ? "m3-rail-brand-label" : "sr-only"}>Privacy Policy<br />Analyzer</span>
          <button type="button" className="m3-rail-toggle" aria-label={expanded ? "Collapse navigation rail" : "Expand navigation rail"} title={expanded ? "Collapse navigation rail" : "Expand navigation rail"} onClick={() => setExpanded((value) => !value)}>{expanded ? icons.collapse : icons.expand}</button>
        </div>
        <div className="m3-rail-create-wrap relative">
          <div className="m3-rail-create-group">
            <button type="button" className="m3-rail-create" aria-label="Add company" title="Add company" onClick={onAddCompany}>{icons.add}<span className={expanded ? "" : "sr-only"}>Add company</span></button>
            {expanded && <button type="button" className="m3-rail-create-more" aria-label="More ways to add companies" aria-expanded={showCreateMenu} onClick={() => setShowCreateMenu((value) => !value)}><MaterialIcon src={moreIcon} /></button>}
          </div>
          {showCreateMenu && <div className="m3-menu absolute left-3 top-[3.5rem] z-30 w-56 p-1"><button className="m3-menu-item w-full px-3 text-left" onClick={() => { setShowCreateMenu(false); setShowImport(true); }}>Import companies from CSV</button></div>}
        </div>
        <div className="flex flex-col gap-1 px-3">
          <RailItem active={workspace === "companies"} label="Companies" icon={icons.companies} expanded={expanded} onClick={() => onWorkspaceChange("companies")} />
          <RailItem active={workspace === "collections"} label="Collections" icon={icons.collections} expanded={expanded} onClick={() => onWorkspaceChange("collections")} />
          <RailItem active={workspace === "scheduled"} label="Scheduled" icon={icons.scheduled} expanded={expanded} onClick={() => onWorkspaceChange("scheduled")} />
        </div>
        <div className="m3-rail-utilities"><RailItem active={workspace === "about"} label="Settings" icon={icons.settings} expanded={expanded} onClick={() => onWorkspaceChange("about")} /></div>
      </nav>

      <nav aria-label="Primary navigation" className="global-bottom-navigation sm:hidden">
        <RailItem active={workspace === "companies"} label="Companies" icon={icons.companies} expanded onClick={() => onWorkspaceChange("companies")} />
        <RailItem active={workspace === "collections"} label="Collections" icon={icons.collections} expanded onClick={() => onWorkspaceChange("collections")} />
        <RailItem active={workspace === "scheduled"} label="Scheduled" icon={icons.scheduled} expanded onClick={() => onWorkspaceChange("scheduled")} />
        <RailItem active={workspace === "about"} label="Settings" icon={icons.settings} expanded onClick={() => onWorkspaceChange("about")} />
      </nav>
      {showImport && <ImportCsvModal onClose={() => setShowImport(false)} />}
    </>
  );
}
