function test_spt_batch_global_gap_integration
% End-to-end detection + linking smoke test using a temporary TIFF movie.

test_dir = fileparts(mfilename('fullpath'));
repo_root = fileparts(test_dir);
pipeline = fullfile(repo_root, 'trajectory_extraction', 'pipeline');
addpath(pipeline);
addpath(fullfile(pipeline, 'matlab_deps'));

scratch = tempname;
mkdir(scratch);
cleanup = onCleanup(@() rmdir(scratch, 's')); %#ok<NASGU>
tif_path = fullfile(scratch, 'synthetic_global_gap.tif');
out_dir = fullfile(scratch, 'output');
mkdir(out_dir);

image_size = 64;
[xx, yy] = meshgrid(1:image_size, 1:image_size);
detection_frames = [1, 2, 3, 5, 6, 7];
for frame_index = 1:7
    frame = ones(image_size, image_size, 'single') * 100;
    if ismember(frame_index, detection_frames)
        center_x = 31 + 0.15 * frame_index;
        center_y = 33 + 0.10 * frame_index;
        gaussian = 5000 * exp( ...
            -((xx - center_x).^2 + (yy - center_y).^2) / (2 * 1.4^2) ...
        );
        frame = frame + gaussian;
    end
    frame = uint16(round(frame));
    if frame_index == 1
        imwrite(frame, tif_path, 'tif', 'Compression', 'none');
    else
        imwrite( ...
            frame, tif_path, 'tif', ...
            'WriteMode', 'append', 'Compression', 'none' ...
        );
    end
end

% All production parameters remain inside spt_batch. The explicit max step
% avoids metadata-dependent calibration in this synthetic fixture.
spt_batch(tif_path, 1.0, 0.1, out_dir, false, 2.0);
result = load(fullfile(out_dir, 'synthetic_global_gap.mat'));

assert(result.sptpara.trackMem == 3);
assert(result.sptpara.mtl == 3);
assert(result.sptpara.max_disp == 2.0);
assert(numel(result.traj) == 1);
assert(result.traj(1).length == 5);
assert(isequal(result.traj(1).pos(:,3), detection_frames'));
assert(result.im.planeAttr(4).nparticle == 0);

fprintf('SPT_BATCH_GLOBAL_GAP_INTEGRATION_OK\n');
end
