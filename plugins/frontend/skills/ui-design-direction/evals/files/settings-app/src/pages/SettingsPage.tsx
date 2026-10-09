import { Button } from '../components/Button';
import { Card } from '../components/Card';
import './SettingsPage.css';

export function SettingsPage() {
  return (
    <main className="settings">
      <h1 className="settings__title">Workspace settings</h1>

      <Card title="Profile" description="The name and URL your teammates see.">
        <label className="settings__field">
          Workspace name
          <input name="name" defaultValue="Northwind Ops" />
        </label>
        <Button>Save changes</Button>
      </Card>

      <Card title="Notifications" description="Choose when we email workspace admins.">
        <label className="settings__check">
          <input type="checkbox" defaultChecked /> Weekly usage summary
        </label>
        <Button variant="secondary">Send a test email</Button>
      </Card>
    </main>
  );
}
