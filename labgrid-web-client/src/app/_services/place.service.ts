import { Injectable } from '@angular/core';

import * as autobahn from 'autobahn-browser';

import { BehaviorSubject } from 'rxjs';

import { Place } from '../../models/place';
import { environment } from 'src/environments/environment';

@Injectable({
    providedIn: 'root',
})
export class PlaceService {
    private session: any;

    public places = new BehaviorSubject<Place[]>([]);

    constructor() {
        const connection = new autobahn.Connection({
            url: environment.labbyURL,
            realm: 'frontend',
        });

        let service = this;
        connection.onopen = async function (session: any, details: any) {
            service.session = session;
        };

        connection.open();
    }

    public async getPlaces(): Promise<Place[]> {
        // If the session is already set, the places can immediately be read.
        // Otherwise the service waits for 1 second.
        if (this.session === undefined) {
            await new Promise((resolve, reject) => {
                setTimeout(resolve, 1000);
            });
        }

        const places = await this.session.call('localhost.places');
        this.places.next(places);
        return places;
    }

    public async getPlace(placeName: string): Promise<Place> {
        // If the session is already set, the requested place can immediately be read.
        // Otherwise the service waits for 1 second.
        if (this.session === undefined) {
            await new Promise((resolve, reject) => {
                setTimeout(resolve, 1000);
            });
        }

        const place = (await this.session.call('localhost.places', [placeName]))[0] as Place;
        return place;
    }

    public async acquirePlace(
        placeName: string,
        username: string
    ): Promise<{ successful: boolean; errorMessage: string }> {

        const acquire = await this.session.call('localhost.acquire', [
            placeName, username,
        ]);

        if (acquire === true) {
            return { successful: true, errorMessage: '' };
        } else if (acquire === false) {
            return { successful: false, errorMessage: 'An unknown error occured!' };
        } else {
            return { successful: false, errorMessage: acquire.error.message };
        }
    }

    public async releasePlace(placeName: string): Promise<{ successful: boolean; errorMessage: string }> {
        const release = await this.session.call('localhost.release', [placeName]);

        if (release === true) {
            return { successful: true, errorMessage: 'An unknown error occured!' };
        } else {
            return { successful: false, errorMessage: release.error.message };
        }
    }

    public async reservePlace(placeName: string, username: string): Promise<any> {
        let result = await this.session.call('localhost.create_reservation', [placeName, username]);
        return result;
    }

    public async getReservations(): Promise<any> {
        return await this.session.call('localhost.get_reservations');
    }

    public async createNewPlace(placeName: string): Promise<{ successful: boolean; errorMessage: string }> {
        let response = await this.session.call('localhost.create_place', [placeName]);

        if (response === true) {
            return { successful: true, errorMessage: '' };
        } else if (response === false) {
            return { successful: false, errorMessage: 'An unknown error occured!' };
        } else {
            return { successful: false, errorMessage: response.error.message };
        }
    }

    public async createNewResource(resourceName: string): Promise<{ successful: boolean; errorMessage: string }> {
        let response = await this.session.call('localhost.create_resource', [resourceName]);
        if (response === true) {
            return { successful: true, errorMessage: '' };
        } else if (response === false) {
            return { successful: false, errorMessage: 'An unknown error occured!' };
        } else {
            return { successful: false, errorMessage: response.error.message };
        }
    }

    public async deletePlace(placeName: string): Promise<{ successful: boolean; errorMessage: string }> {
        let response = await this.session.call('localhost.delete_place', [placeName]);

        if (response === true) {
            return { successful: true, errorMessage: '' };
        } else if (response === false) {
            return { successful: false, errorMessage: 'An unknown error occured!' };
        } else {
            return { successful: false, errorMessage: response.error.message };
        }
    }

    public async resetPlace(placeName: string): Promise<boolean> {
        let response = await this.session.call('localhost.reset', [placeName]);

        if (response === true) {
            return true;
        } else {
            return false;
        }
    }
}
