# labgrid-frontend-mle
A web frontend for labgrid in cooperation with MLE.

## Python Router

See [python-wamp-client](https://github.com/Simon-Deuring/labgrid-frontend-mle/tree/main/python-wamp-client) for further information.

## Web Client

### Quick Start

For a quick start you can copy the content of labgrid-web-client/dist and host it on a web server. The dist folder contains a pre-built version of the web frontend.

### DevEnvironment
For the development tasks, angular needs nodejs, npm and npm modules in the right version installed.
The web frontend is developed in an old version - anyone who can upgrade it, is welcome to do so.
For now, try to install:

- [ ] nodejs v. 16
  - [ ] `curl -fsSL https://deb.nodesource.com/setup_16.x | sudo -E bash -`
  - [ ] `sudo apt autoremove nodejs` (if you had another nodejs version installed previously)
  - [ ] `sudo apt install nodejs`
  - [ ] `node -v` should be v16.20.2
- [ ] npm
  - [ ] `sudo apt install npm` (i.f not installed already).
  - [ ] `sudo npm install -g npm@8.1.2`
  - [ ] `npm -v` should be 8.1.2
- [ ] angular cli (`ng`) and other modules
  - [ ] `cd <this workspace root directory, next to package.json>`
  - [ ] `sudo npm install production=false` 
  - [ ] `sudo npm install -g @angular/cli@13`
  - [ ] `ng v` should be 13.3.11
  - **IF NOT** then clean up: 
    - [ ] `sudo npm prune` - clean up all the packages not in the dependencies, you might have installed previously
    - [ ] `sudo npm install -g @angular/cli@13`

This might not be the optimal way to do it (or so to say: better not do it, especially when put into fire),
but with my limited knowledge about angular I am just glad it somehow works.

### Development

Run `npm run start` to start a development server. Then navigate to `http://localhost:4200/`. The app will automatically reload if you change any of the source files.

### Linting and Code Formatting

**Before creating a new pull request** you should run `npm run lint`. This triggers ESLint and Prettier and directly fixes all discovered problems. Additionally, every time a file is saved Prettier is called to guarantee high code quality.

### Building

Run `npm run build` to build the project. The build artifacts will be stored in the `dist/` directory.

### Running Unit Tests

Run `npm run test` to execute the unit tests via [Karma](https://karma-runner.github.io).

### Code Scaffolding

Run `ng generate component component-name` to generate a new component. You can also use `ng generate directive|pipe|service|class|guard|interface|enum|module`.

### Further Help

To get more help on the Angular CLI use `ng help` or go check out the [Angular CLI Overview and Command Reference](https://angular.io/cli) page.
