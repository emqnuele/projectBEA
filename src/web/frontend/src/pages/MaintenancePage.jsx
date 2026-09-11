import React from 'react';
import { UpdatePanel } from '../components/maintenance/UpdatePanel';
import { DoctorPanel } from '../components/maintenance/DoctorPanel';

/**
 * The two things you do to an install rather than to her: update it, and find
 * out why it is not working.
 *
 * Both existed already — one as `make update`, one as `bea --doctor` — and both
 * were invisible to everyone who runs her from this screen and never opens a
 * terminal, which is most people.
 */
export default function MaintenancePage() {
    return (
        <div className="h-full overflow-y-auto pb-2 pr-0.5">
            <div className="mx-auto flex max-w-3xl flex-col gap-2.5">
                <UpdatePanel />
                <DoctorPanel />
            </div>
        </div>
    );
}
