import click
import piv_functions
import show_functions


@click.group()
def cli():
    pass


@click.command()
@click.argument('before_height', type=click.Path(exists=True, readable=True))
@click.argument('after_height', type=click.Path(exists=True, readable=True))
@click.argument('template_size', type=click.IntRange(3, None))
@click.argument('step_size', type=click.IntRange(1, None))
@click.option('--prop', nargs=2, type=click.Path(exists=True, readable=True), help='Option to propagate error. Requires two arguments: 1) pre-event uncertainties in GeoTIFF format, 2) post-event uncertainties in GeoTIFF format.')
@click.option('--outname', type=str, help='Optional base filename to use for output files.')
def piv(before_height, after_height, template_size, step_size, prop, outname):
    '''
    Runs PIV on a pair pre- and post-event DEMs.

    \b
    Arguments: BEFORE_HEIGHT  Pre-event DEM in GeoTIFF format
               AFTER_HEIGHT   Post-event DEM in GeoTIFF format
               TEMPLATE_SIZE  Size of square correlation template in pixels
               STEP_SIZE      Size of template step in pixels
    '''
    if prop:
        propagate = True
        before_uncertainty = prop[0]
        after_uncertainty = prop[1]
    else:
        propagate = False
        before_uncertainty = ''
        after_uncertainty = ''
    
    if outname:
        output_base_name = outname + '_'
    else:
        output_base_name = ''

    piv_functions.piv(before_height, after_height, 
                      template_size, step_size, 
                      before_uncertainty, after_uncertainty,
                      propagate, output_base_name)


@click.command()
@click.argument('background_image', type=click.Path(exists=True, readable=True))
@click.option('--vec', type=click.Path(exists=True, readable=True), help="Option to overlay PIV vectors on the background image. Requires the json file of PIV vectors generated by the 'piv' command.")
@click.option('--ell', type=click.Path(exists=True, readable=True), help="Option to overlay PIV uncertainty ellipses on the background image. Requires the json file of covariance matrices generated when running the 'piv' command with the 'prop' option.")
@click.option('--vecscale', type=float, help='Option to scale the displayed PIV vectors. Requires a numeric scale factor.')
@click.option('--ellscale', type=float, help='Option to scale the displayed uncertainty ellipses. Requires a numeric scale factor.')
def pivshow(background_image, vec, ell, vecscale, ellscale):
    '''
    Optionally displays PIV displacement vectors and/or uncertainty ellipses over a background image.
    
    Arguments: BACKGROUND_IMAGE  Background image in GeoTIFF format
    '''
    show_functions.show(background_image, vec, ell, vecscale, ellscale)


cli.add_command(piv)
cli.add_command(pivshow)

if __name__ == '__main__':
    cli()
