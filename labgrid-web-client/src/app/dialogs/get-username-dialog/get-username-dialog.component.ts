//import { Component, OnInit } from '@angular/core';
import { Component, Inject } from '@angular/core';
import { MatDialogRef, MAT_DIALOG_DATA } from '@angular/material/dialog';

@Component({
  selector: 'app-get-username-dialog',
  templateUrl: './get-username-dialog.component.html',
  styleUrls: ['./get-username-dialog.component.css']
})
export class GetUsernameDialogComponent {

  constructor(
        public dialogRef: MatDialogRef<GetUsernameDialogComponent>,
        @Inject(MAT_DIALOG_DATA) public username: string
  ) {
      let a = document.getElementById('username');
      if (a !== null) { a.focus(); }
  }

//  ngOnInit(): void {
//  }

}
