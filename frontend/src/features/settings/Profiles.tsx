import React from "react";
import { api, type ApiError, type NetworkProfile } from "../../api";

export function Profiles({
  profiles,
  onReload,
}: {
  profiles: NetworkProfile[];
  onReload: () => void;
}) {
  const [name, setName] = React.useState("");
  const [description, setDescription] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState("");
  const [notice, setNotice] = React.useState("");

  async function add(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api<NetworkProfile>("/profiles", {
        method: "POST",
        body: JSON.stringify({ name, description }),
      });
      setName("");
      setDescription("");
      setNotice("Profile created. Add an approved range to use it.");
      onReload();
    } catch (cause) {
      setError((cause as ApiError).message || "Could not create profile.");
    } finally {
      setBusy(false);
    }
  }

  async function download(profile: NetworkProfile) {
    setError("");
    try {
      const plan = await api<object>(`/profiles/${profile.id}/export`);
      const url = URL.createObjectURL(
        new Blob([JSON.stringify(plan, null, 2)], { type: "application/json" }),
      );
      const link = document.createElement("a");
      link.href = url;
      link.download = `netsentinel-profile-${profile.id}.json`;
      link.click();
      URL.revokeObjectURL(url);
    } catch (cause) {
      setError((cause as ApiError).message || "Could not export profile.");
    }
  }

  return (
    <div className="panel">
      <h2>Network profiles</h2>
      <p className="muted">
        Group approved ranges by network. Exported plans contain private CIDRs
        and require fresh approval before use elsewhere.
      </p>
      <form onSubmit={add}>
        <label htmlFor="profile-name">New profile name</label>
        <input
          id="profile-name"
          maxLength={100}
          required
          value={name}
          onChange={(event) => setName(event.target.value)}
        />
        <label htmlFor="profile-description">Description</label>
        <input
          id="profile-description"
          maxLength={500}
          value={description}
          onChange={(event) => setDescription(event.target.value)}
        />
        <button className="secondary" disabled={busy}>
          {busy ? "Creating…" : "Create profile"}
        </button>
      </form>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {notice && (
        <p className="success" role="status">
          {notice}
        </p>
      )}
      <ul className="scope-list">
        {profiles.map((profile) => (
          <li key={profile.id}>
            <div>
              <strong>{profile.name}</strong>
              <small>
                {profile.scope_count} approved ranges · {profile.description}
              </small>
            </div>
            <button className="secondary" onClick={() => download(profile)}>
              Export plan
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
