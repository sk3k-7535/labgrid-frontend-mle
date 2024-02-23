//import { Component, OnInit } from '@angular/core';
import { Component, Inject } from '@angular/core';
import { MatDialogRef, MAT_DIALOG_DATA } from '@angular/material/dialog';
import { MatSnackBar } from '@angular/material/snack-bar';

@Component({
  selector: 'app-get-username-dialog',
  templateUrl: './get-username-dialog.component.html',
  styleUrls: ['./get-username-dialog.component.css']
})
export class GetUsernameDialogComponent {

  constructor(
        public dialogRef: MatDialogRef<GetUsernameDialogComponent>,
        @Inject(MAT_DIALOG_DATA) public username: string,
        private _snackBar: MatSnackBar
  ) {}

  save() {
    if (this.username.includes("/")) { this.dialogRef.close(this.username) }
    else {this._snackBar.open("Do use a '/' in the username, please");}
  }

//  ngOnInit(): void {
//  }

}
